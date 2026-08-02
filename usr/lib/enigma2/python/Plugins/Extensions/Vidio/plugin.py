# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import time
try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.config import ConfigInteger, ConfigSubsection, ConfigText, config, configfile
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.Directories import fileExists
from enigma import eConsoleAppContainer, eServiceCenter, eServiceReference

from . import PLUGIN_VERSION

PLUGIN_NAME = "Vidio"
CONFIG_DIR = "/etc/vidio"
PID_FILE = "/var/run/vidio-ffmpeg.pid"
FFMPEG = "/usr/bin/ffmpeg"
STREAM_URL = "http://127.0.0.1/web/stream.m3u?ref=%s"
TIMESHIFT_PATHS = ("/media/hdd", "/media/usb")

config.plugins.vidio = ConfigSubsection()
config.plugins.vidio.audio_ref = ConfigText(default="", fixed_size=False)
config.plugins.vidio.audio_name = ConfigText(default="", fixed_size=False)
config.plugins.vidio.video_delay_tenths = ConfigInteger(default=0, limits=(0, 600))


def toText(value):
    if value is None:
        return ""
    try:
        if isinstance(value, unicode):
            return value.encode("utf-8")
    except NameError:
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
    return str(value)


def ensureConfigDir():
    try:
        if not os.path.isdir(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
    except OSError:
        pass


def connectSignal(signal, callback):
    if hasattr(signal, "connect"):
        return signal.connect(callback)
    if hasattr(signal, "get"):
        signal.get().append(callback)
        return None
    signal.append(callback)
    return None


def timeshiftStoragePath():
    for path in TIMESHIFT_PATHS:
        if os.path.isdir(path) and os.access(path, os.W_OK):
            return path
    return ""


def killPreviousFfmpeg():
    try:
        with open(PID_FILE, "r") as source:
            pid = int(source.readline().strip())
        os.kill(pid, 15)
    except Exception:
        pass
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass


def currentServiceReference(session):
    service = session.nav.getCurrentlyPlayingServiceReference()
    if service is None:
        return ""
    return service.toString()


def serviceName(ref):
    info = eServiceCenter.getInstance().info(ref)
    if info:
        name = info.getName(ref)
        return toText(name).replace("\xc2\x86", "").replace("\xc2\x87", "")
    return ref.toString()


def listServices(root):
    result = []
    serviceHandler = eServiceCenter.getInstance()
    listing = serviceHandler.list(root)
    if listing is None:
        return result
    while True:
        ref = listing.getNext()
        if not ref.valid():
            break
        flags = ref.flags
        name = serviceName(ref)
        result.append((name, ref, flags))
    return result


class VidioServiceBrowser(Screen):
    skin = """
    <screen name="VidioServiceBrowser" position="center,center" size="900,620" title="Vidio - Select audio service">
        <widget name="title" position="20,16" size="860,34" font="Regular;24" />
        <widget name="list" position="20,60" size="860,500" scrollbarMode="showOnDemand" />
        <widget name="help" position="20,570" size="860,32" font="Regular;20" />
    </screen>
    """

    def __init__(self, session, callback=None):
        Screen.__init__(self, session)
        self.callback = callback
        self.path = []
        self["title"] = Label("Bouquets")
        self["help"] = Label("OK: open/select    Exit: back")
        self["list"] = MenuList([])
        self["actions"] = ActionMap(
            ["OkCancelActions"],
            {"ok": self.ok, "cancel": self.cancel},
            -1,
        )
        self.onLayoutFinish.append(self.showBouquets)

    def setItems(self, title, items):
        self["title"].setText(title)
        self["list"].setList(items)

    def showBouquets(self):
        roots = [
            eServiceReference("1:7:1:0:0:0:0:0:0:0:(type == 1) FROM BOUQUET \"bouquets.tv\" ORDER BY bouquet"),
            eServiceReference("1:7:1:0:0:0:0:0:0:0:(type == 1) ORDER BY name"),
        ]
        items = []
        for root in roots:
            for name, ref, flags in listServices(root):
                items.append((name, ref, flags))
        self.path = []
        self.setItems("Bouquets and service lists", items)

    def openDirectory(self, name, ref):
        self.path.append((name, ref))
        self.setItems(name, listServices(ref))

    def ok(self):
        current = self["list"].getCurrent()
        if current is None:
            return
        name, ref, flags = current
        if flags & eServiceReference.isDirectory:
            self.openDirectory(name, ref)
            return
        if self.callback:
            self.callback(name, ref.toString())
        self.close()

    def cancel(self):
        if self.path:
            self.path.pop()
            if not self.path:
                self.showBouquets()
            else:
                name, ref = self.path[-1]
                self.setItems(name, listServices(ref))
            return
        self.close()


class VidioScreen(Screen):
    skin = """
    <screen name="VidioScreen" position="center,center" size="900,430" title="Vidio">
        <widget name="header" position="24,18" size="852,34" font="Regular;26" />
        <widget name="status" position="24,64" size="852,80" font="Regular;21" />
        <widget name="audio" position="24,158" size="852,34" font="Regular;24" />
        <widget name="delay" position="24,206" size="852,34" font="Regular;24" />
        <widget name="tuner" position="24,254" size="852,58" font="Regular;21" />
        <ePixmap pixmap="skin_default/buttons/red.png" position="24,358" size="140,40" alphatest="on" />
        <ePixmap pixmap="skin_default/buttons/green.png" position="184,358" size="140,40" alphatest="on" />
        <widget name="red" position="24,358" size="140,40" font="Regular;20" halign="center" valign="center" transparent="1" />
        <widget name="green" position="184,358" size="140,40" font="Regular;20" halign="center" valign="center" transparent="1" />
        <widget name="help" position="344,362" size="532,32" font="Regular;20" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.container = eConsoleAppContainer()
        self.delayTenths = int(config.plugins.vidio.video_delay_tenths.value)
        self.audioName = config.plugins.vidio.audio_name.value
        self.audioRef = config.plugins.vidio.audio_ref.value
        self.started = False
        self.timeshiftStartedAt = None
        self.originalAudioTrack = None

        self["header"] = Label("Vidio %s" % PLUGIN_VERSION)
        self["status"] = Label("")
        self["audio"] = Label("")
        self["delay"] = Label("")
        self["tuner"] = Label("")
        self["red"] = Label("Stop")
        self["green"] = Label("Save")
        self["help"] = Label("OK: audio service    Left/Right: video delay 0.1s    Exit: close")
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions"],
            {
                "ok": self.chooseAudio,
                "cancel": self.close,
                "left": self.delayDown,
                "right": self.delayUp,
                "green": self.save,
                "red": self.stop,
            },
            -1,
        )
        self.onLayoutFinish.append(self.refresh)
        self.onClose.append(self.cleanup)

    def refresh(self):
        current = currentServiceReference(self.session)
        audio = self.audioName or "No audio service selected"
        self["audio"].setText("Audio source: %s" % audio)
        self["delay"].setText("Video delay: %.1f seconds" % (self.delayTenths / 10.0))
        self["tuner"].setText(self.tunerStatus(current))
        self["status"].setText(self.statusText())

    def statusText(self):
        if not fileExists(FFMPEG):
            return "ffmpeg was not found at %s." % FFMPEG
        if not self.audioRef:
            return "Select a second service for replacement audio."
        if self.delayTenths > 0 and not timeshiftStoragePath():
            return "Video delay needs writable timeshift storage at /media/hdd or /media/usb."
        if self.started:
            return "Running. Current channel audio should be muted/replaced by the selected service."
        return "Ready. Press Green to save and start."

    def tunerStatus(self, current):
        if not current:
            return "Current video service: unknown"
        same = current == self.audioRef
        text = "Current video ref: %s" % current[:95]
        if same:
            text += "\nAudio source is the current service; choose a different tuner/service."
        else:
            text += "\nDreamOS will allocate the second service if a tuner is free or compatible."
        return text

    def chooseAudio(self):
        self.session.open(VidioServiceBrowser, callback=self.audioSelected)

    def audioSelected(self, name, ref):
        self.audioName = name
        self.audioRef = ref
        self.refresh()

    def delayDown(self):
        if self.delayTenths > 0:
            self.delayTenths -= 1
        self.refresh()

    def delayUp(self):
        if self.delayTenths < 600:
            self.delayTenths += 1
        self.refresh()

    def save(self):
        ensureConfigDir()
        config.plugins.vidio.audio_name.value = self.audioName
        config.plugins.vidio.audio_ref.value = self.audioRef
        config.plugins.vidio.video_delay_tenths.value = int(self.delayTenths)
        config.plugins.vidio.save()
        configfile.save()
        self.start()

    def start(self):
        if not self.audioRef:
            self.session.open(MessageBox, "Select an audio service first.", MessageBox.TYPE_INFO, timeout=5)
            return
        if not fileExists(FFMPEG):
            self.session.open(MessageBox, "ffmpeg is missing: %s" % FFMPEG, MessageBox.TYPE_ERROR)
            return
        if self.delayTenths > 0 and not timeshiftStoragePath():
            self.session.open(
                MessageBox,
                "Video delay needs writable timeshift storage at /media/hdd or /media/usb.",
                MessageBox.TYPE_ERROR,
            )
            return
        self.startTimeshiftDelay()
        self.muteCurrentServiceAudio()
        self.startAudio()
        self.started = True
        self.refresh()

    def startTimeshiftDelay(self):
        if self.delayTenths <= 0:
            return
        service = self.session.nav.getCurrentService()
        if service is None:
            return
        pause = service.pause()
        if pause is None:
            self.session.open(MessageBox, "This service does not expose pause/timeshift control.", MessageBox.TYPE_ERROR)
            return
        try:
            pause.pause()
            self.timeshiftStartedAt = time.time()
            delaySeconds = self.delayTenths / 10.0
            self.session.openWithCallback(
                self.resumeAfterDelay,
                MessageBox,
                "Buffering video for %.1f seconds..." % delaySeconds,
                MessageBox.TYPE_INFO,
                timeout=max(1, int(delaySeconds)),
            )
        except Exception as error:
            self.session.open(MessageBox, "Could not start video delay: %s" % error, MessageBox.TYPE_ERROR)

    def resumeAfterDelay(self, *args):
        try:
            service = self.session.nav.getCurrentService()
            pause = service and service.pause()
            if pause:
                pause.unpause()
        except Exception:
            pass

    def startAudio(self):
        killPreviousFfmpeg()
        encoded = quote(self.audioRef, safe="")
        url = STREAM_URL % encoded
        command = (
            '%s -hide_banner -loglevel warning -nostdin -i "%s" '
            '-vn -ac 2 -f alsa default'
        ) % (FFMPEG, url)
        self.container.execute(command)
        try:
            pid = self.container.getPID()
            with open(PID_FILE, "w") as target:
                target.write("%s\n" % pid)
        except Exception:
            pass

    def muteCurrentServiceAudio(self):
        try:
            service = self.session.nav.getCurrentService()
            tracks = service and service.audioTracks()
            if not tracks:
                return
            try:
                self.originalAudioTrack = tracks.getCurrentTrack()
            except Exception:
                self.originalAudioTrack = None
            tracks.selectTrack(-1)
        except Exception:
            self.session.open(
                MessageBox,
                "Could not disable the current service audio. If you hear both channels, mute this service manually for this test.",
                MessageBox.TYPE_INFO,
                timeout=7,
            )

    def restoreCurrentServiceAudio(self):
        if self.originalAudioTrack is None:
            return
        try:
            service = self.session.nav.getCurrentService()
            tracks = service and service.audioTracks()
            if tracks:
                tracks.selectTrack(self.originalAudioTrack)
        except Exception:
            pass

    def stop(self):
        killPreviousFfmpeg()
        try:
            self.container.kill()
        except Exception:
            pass
        self.restoreCurrentServiceAudio()
        self.started = False
        self.refresh()

    def cleanup(self):
        pass


def openVidio(session, **kwargs):
    session.open(VidioScreen)


def autostart(reason, **kwargs):
    if reason == 1:
        killPreviousFfmpeg()


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name=PLUGIN_NAME,
            description="Replace current audio with another service and delay video",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            fnc=openVidio,
        ),
        PluginDescriptor(
            name=PLUGIN_NAME,
            description="Vidio startup cleanup",
            where=PluginDescriptor.WHERE_AUTOSTART,
            fnc=autostart,
        ),
    ]
