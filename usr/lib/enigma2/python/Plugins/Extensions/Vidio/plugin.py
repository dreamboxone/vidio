# -*- coding: utf-8 -*-
from __future__ import print_function

import os

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.config import ConfigInteger, ConfigSubsection, ConfigText, ConfigYesNo, config, configfile
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.Directories import fileExists
from enigma import eConsoleAppContainer, eServiceCenter, eServiceReference, eTimer, iPlayableService

from . import PLUGIN_VERSION
from .core import DEFAULT_OUTPUT_URL, build_ffmpeg_args, concise_ffmpeg_error, is_dvb_service

PLUGIN_NAME = "Vidio"
PID_FILE = "/var/run/vidio-ffmpeg.pid"
LOG_FILE = "/tmp/vidio-ffmpeg.log"
FFMPEG = "/usr/bin/ffmpeg"
KEYMAP_FILE = os.path.join(os.path.dirname(__file__), "keymap.xml")
KEYMAP_LOADED = False

EV_START = getattr(iPlayableService, "evStart", None)
EV_VIDEO_PTS_VALID = getattr(iPlayableService, "evVideoPtsValid", None)
EV_UPDATED_INFO = getattr(iPlayableService, "evUpdatedInfo", None)
EV_TUNE_FAILED = getattr(iPlayableService, "evTuneFailed", None)
EV_EOF = getattr(iPlayableService, "evEOF", None)

config.plugins.vidio = ConfigSubsection()
config.plugins.vidio.enabled = ConfigYesNo(default=False)
config.plugins.vidio.audio_ref = ConfigText(default="", fixed_size=False)
config.plugins.vidio.audio_name = ConfigText(default="", fixed_size=False)
config.plugins.vidio.video_delay_tenths = ConfigInteger(default=0, limits=(0, 300))


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


def fitText(value, maximum):
    text = toText(value)
    if len(text) <= maximum:
        return text
    return text[:maximum - 3] + "..."


def persistEnabled(value):
    config.plugins.vidio.enabled.value = bool(value)
    config.plugins.vidio.enabled.save()
    configfile.save()


def connectSignal(signal, callback):
    if hasattr(signal, "connect"):
        return signal.connect(callback)
    if hasattr(signal, "get"):
        signal.get().append(callback)
        return None
    signal.append(callback)
    return None


def removePidFile():
    try:
        os.unlink(PID_FILE)
    except OSError:
        pass


def killPreviousFfmpeg():
    try:
        with open(PID_FILE, "r") as source:
            pid = int(source.readline().strip())
        commandLine = ""
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as source:
                commandLine = toText(source.read()).replace("\x00", " ")
        except Exception:
            pass
        if "ffmpeg" in commandLine and "127.0.0.1:17999" in commandLine:
            os.kill(pid, 15)
    except Exception:
        pass
    removePidFile()


def currentServiceReference(session):
    ref = session.nav.getCurrentlyPlayingServiceReference()
    return ref.toString() if ref is not None else ""


def serviceName(ref):
    info = eServiceCenter.getInstance().info(ref)
    if info:
        name = info.getName(ref)
        return toText(name).replace("\xc2\x86", "").replace("\xc2\x87", "")
    return ref.toString()


def listServices(root):
    result = []
    listing = eServiceCenter.getInstance().list(root)
    if listing is None:
        return result
    while True:
        ref = listing.getNext()
        if not ref.valid():
            break
        result.append((serviceName(ref), ref, ref.flags))
    return result


class VidioEngine(object):
    STOPPED = "stopped"
    STARTING = "starting"
    BUFFERING = "buffering"
    RUNNING = "running"
    ERROR = "error"

    def __init__(self):
        self.session = None
        self.state = self.STOPPED
        self.status = "Stopped."
        self.lastError = ""
        self.container = None
        self.dataConnection = None
        self.closedConnection = None
        self.timer = eTimer()
        self.timerConnection = connectSignal(self.timer.timeout, self._timerFired)
        self.timerAction = None
        self.listeners = []
        self.navHooked = False
        self.stopping = False
        self.localRequested = False
        self.outputReady = False
        self.videoConfirmed = False
        self.sourceVideoRef = ""
        self.sourceVideoName = ""
        self.audioRef = ""
        self.audioName = ""
        self.delayTenths = 0
        self.originalRef = None
        self.localRef = None
        self.log = ""
        self.pendingStart = None

    def setSession(self, session):
        if self.session is session:
            return
        if self.session is not None and self.navHooked:
            try:
                self.session.nav.event.remove(self._navEvent)
            except Exception:
                pass
        self.session = session
        self.navHooked = False
        if session is not None:
            try:
                session.nav.event.append(self._navEvent)
                self.navHooked = True
            except Exception:
                pass

    def addListener(self, callback):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def removeListener(self, callback):
        try:
            self.listeners.remove(callback)
        except ValueError:
            pass

    def notify(self, kind="state"):
        for callback in list(self.listeners):
            try:
                callback(kind, self.status)
            except Exception:
                pass

    def isActive(self):
        return self.state in (self.STARTING, self.BUFFERING, self.RUNNING)

    def _setState(self, state, status, kind="state"):
        self.state = state
        self.status = status
        self.notify(kind)

    def _schedule(self, action, milliseconds):
        self.timer.stop()
        self.timerAction = action
        self.timer.start(int(milliseconds), True)

    def _timerFired(self):
        action = self.timerAction
        self.timerAction = None
        if action:
            action()

    def start(self, session, videoRef, videoName, audioRef, audioName, delayTenths):
        self.setSession(session)
        settings = (videoRef, videoName, audioRef, audioName, int(delayTenths))
        if self.isActive() or self.state == self.ERROR:
            self.pendingStart = settings
            self.stop(restore=True, clearPending=False)
            self._setState(self.STARTING, "Restarting Vidio...")
            self._schedule(self._startPending, 700)
            return True
        self.pendingStart = settings
        return self._startPending()

    def _startPending(self):
        if not self.pendingStart:
            return False
        videoRef, videoName, audioRef, audioName, delayTenths = self.pendingStart
        self.pendingStart = None
        if not fileExists(FFMPEG):
            self.fail("ffmpeg is missing: %s" % FFMPEG, restore=False)
            return False
        if not is_dvb_service(videoRef) or not is_dvb_service(audioRef):
            self.fail("Vidio currently supports DVB satellite services only.", restore=False)
            return False
        if videoRef == audioRef:
            self.fail("Video and audio services must be different.", restore=False)
            return False

        self.sourceVideoRef = videoRef
        self.sourceVideoName = videoName
        self.audioRef = audioRef
        self.audioName = audioName
        self.delayTenths = delayTenths
        self.originalRef = eServiceReference(videoRef)
        self.localRef = eServiceReference(4097, 0, DEFAULT_OUTPUT_URL)
        try:
            self.localRef.setName("Vidio")
        except Exception:
            pass
        self.log = ""
        self.lastError = ""
        self.outputReady = False
        self.videoConfirmed = False
        self.localRequested = False
        self.stopping = False
        persistEnabled(True)
        try:
            with open(LOG_FILE, "w"):
                pass
        except Exception:
            pass
        killPreviousFfmpeg()
        self.container = eConsoleAppContainer()
        self.dataConnection = connectSignal(self.container.dataAvail, self._ffmpegData)
        self.closedConnection = connectSignal(self.container.appClosed, self._ffmpegClosed)
        args = build_ffmpeg_args(FFMPEG, videoRef, audioRef, delayTenths)
        self._writeLog("Vidio command: %s\n" % " ".join(args))
        self._setState(self.STARTING, "Opening both DVB services...")
        result = self.container.execute(*args)
        if result:
            self.container = None
            self.fail("Could not start ffmpeg (error %s)." % result, restore=False)
            return False
        try:
            with open(PID_FILE, "w") as target:
                target.write("%s\n" % self.container.getPID())
        except Exception:
            pass
        self._schedule(self._startupTimedOut, 15000)
        return True

    def _writeLog(self, data):
        text = toText(data)
        self.log = (self.log + text)[-16000:]
        try:
            with open(LOG_FILE, "a") as target:
                target.write(text)
        except Exception:
            pass

    def _ffmpegData(self, data):
        text = toText(data)
        self._writeLog(text)
        if not self.outputReady and ("out_time_ms=" in text or "out_time_us=" in text or "progress=continue" in text):
            self.outputReady = True
            self.timer.stop()
            self._playLocalStream()

    def _playLocalStream(self):
        if self.stopping or not self.container or not self.localRef:
            return
        self.localRequested = True
        self._setState(self.BUFFERING, "Opening the combined Enigma2 stream...")
        try:
            result = self.session.nav.playService(self.localRef, False, True)
        except TypeError:
            result = self.session.nav.playService(self.localRef)
        except Exception as error:
            self.fail("Enigma2 could not open the local stream: %s" % error)
            return
        if result not in (None, 0):
            self.fail("Enigma2 rejected the local combined stream.")
            return
        self._schedule(self._confirmLocalPlayback, 8000)

    def _isLocalCurrent(self):
        if not self.session:
            return False
        ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if ref is None:
            return False
        try:
            if ref.getPath() == DEFAULT_OUTPUT_URL:
                return True
        except Exception:
            pass
        return DEFAULT_OUTPUT_URL in ref.toString()

    def _confirmLocalPlayback(self):
        # OE-Alliance images do not expose DreamOS' evVideoPtsValid event. In
        # that case, current-service identity plus live ffmpeg output is the
        # strongest portable confirmation available from Enigma2's Python API.
        videoReady = self.videoConfirmed or EV_VIDEO_PTS_VALID is None
        if self._isLocalCurrent() and self.container and self.outputReady and videoReady:
            self._setState(
                self.RUNNING,
                "Running. %s video with %s audio." % (self.sourceVideoName, self.audioName),
            )
            return
        self.fail("Enigma2 did not start the local combined stream.")

    def _startupTimedOut(self):
        detail = concise_ffmpeg_error(self.log)
        self.fail("No combined stream was produced. Check both tuners. %s" % detail, restore=False)

    def _ffmpegClosed(self, returnCode):
        removePidFile()
        self.container = None
        if self.stopping:
            return
        if self.state in (self.STARTING, self.BUFFERING, self.RUNNING):
            detail = concise_ffmpeg_error(self.log)
            self.fail("ffmpeg stopped (code %s). %s" % (returnCode, detail))

    def _navEvent(self, event):
        if EV_START is not None and event == EV_START:
            if self.state == self.RUNNING and not self._isLocalCurrent():
                self.stop(restore=False)

        confirmsVideo = EV_VIDEO_PTS_VALID is not None and event == EV_VIDEO_PTS_VALID
        if EV_VIDEO_PTS_VALID is None:
            confirmsVideo = event in tuple(
                value for value in (EV_START, EV_UPDATED_INFO) if value is not None
            )
        if confirmsVideo:
            if self.localRequested and self._isLocalCurrent() and self.outputReady:
                self.videoConfirmed = True
                self.timer.stop()
                self._confirmLocalPlayback()

        failureEvents = tuple(value for value in (EV_TUNE_FAILED, EV_EOF) if value is not None)
        if event in failureEvents:
            if self.localRequested and self.state in (self.BUFFERING, self.RUNNING):
                self.fail("The local combined stream stopped in Enigma2.")

    def fail(self, message, restore=True):
        self.lastError = message
        self._stopProcess()
        if restore:
            self._restoreOriginal()
        persistEnabled(False)
        self._setState(self.ERROR, message, "error")

    def _stopProcess(self):
        self.timer.stop()
        self.timerAction = None
        self.stopping = True
        container = self.container
        self.container = None
        if container is not None:
            try:
                container.kill()
            except Exception:
                pass
        killPreviousFfmpeg()
        self.outputReady = False
        self.videoConfirmed = False
        self.localRequested = False

    def _restoreOriginal(self):
        if self.session is None or self.originalRef is None:
            return
        try:
            self.session.nav.playService(self.originalRef, False, True)
        except TypeError:
            try:
                self.session.nav.playService(self.originalRef)
            except Exception:
                pass
        except Exception:
            pass

    def stop(self, restore=True, clearPending=True):
        if clearPending:
            self.pendingStart = None
        self._stopProcess()
        if restore and self._isLocalCurrent():
            self._restoreOriginal()
        self.stopping = False
        persistEnabled(False)
        self._setState(self.STOPPED, "Stopped. Original channel audio is active.")

    def shutdown(self):
        self.pendingStart = None
        self._stopProcess()
        persistEnabled(False)


ENGINE = VidioEngine()


class VidioServiceBrowser(Screen):
    skin = """
    <screen name="VidioServiceBrowser" position="center,center" size="900,620" title="Vidio - Select audio service">
        <widget name="title" position="20,16" size="860,34" font="Regular;24" />
        <widget name="list" position="20,60" size="860,500" scrollbarMode="showOnDemand" />
        <widget name="help" position="20,570" size="860,32" font="Regular;20" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.path = []
        self["title"] = Label("Bouquets")
        self["help"] = Label("OK: open/select    Exit: back")
        self["list"] = MenuList([])
        self["actions"] = ActionMap(["OkCancelActions"], {"ok": self.ok, "cancel": self.cancel}, -1)
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
        seen = set()
        for root in roots:
            for name, ref, flags in listServices(root):
                key = ref.toString()
                if key not in seen:
                    seen.add(key)
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
        if not is_dvb_service(ref.toString()):
            self.session.open(MessageBox, "Select a DVB satellite service.", MessageBox.TYPE_INFO, timeout=5)
            return
        self.close((name, ref.toString()))

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
    <screen name="VidioScreen" position="center,center" size="820,430" title="Vidio">
        <widget name="header" position="24,18" size="772,34" font="Regular;26" />
        <widget name="status" position="24,58" size="772,58" font="Regular;19" />
        <widget name="list" position="24,126" size="772,170" scrollbarMode="showOnDemand" />
        <widget name="note" position="24,310" size="772,32" font="Regular;18" />
        <widget name="red" position="24,364" size="140,40" font="Regular;20" halign="center" valign="center" foregroundColor="#ffffff" backgroundColor="#b01818" transparent="0" />
        <widget name="green" position="184,364" size="140,40" font="Regular;20" halign="center" valign="center" foregroundColor="#ffffff" backgroundColor="#008a00" transparent="0" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        ENGINE.setSession(session)
        self.enabled = ENGINE.isActive()
        self.delayTenths = int(config.plugins.vidio.video_delay_tenths.value)
        self.audioName = config.plugins.vidio.audio_name.value
        self.audioRef = config.plugins.vidio.audio_ref.value
        self.videoRef = ENGINE.sourceVideoRef if ENGINE.isActive() else currentServiceReference(session)
        try:
            self.videoName = ENGINE.sourceVideoName if ENGINE.isActive() else serviceName(eServiceReference(self.videoRef))
        except Exception:
            self.videoName = "current service"
        self["header"] = Label("Vidio %s" % PLUGIN_VERSION)
        self["status"] = Label("")
        self["list"] = MenuList([])
        self["note"] = Label("Long-press Audio opens this menu from live TV.")
        self["red"] = Label("Exit")
        self["green"] = Label("Save")
        self["actions"] = ActionMap(
            ["OkCancelActions", "DirectionActions", "ColorActions"],
            {
                "ok": self.ok,
                "cancel": self.close,
                "up": self["list"].up,
                "down": self["list"].down,
                "left": self.delayDown,
                "right": self.delayUp,
                "green": self.save,
                "red": self.close,
            },
            -1,
        )
        ENGINE.addListener(self.engineUpdate)
        self.onLayoutFinish.append(self.refresh)
        self.onClose.append(self.cleanup)

    def menuItems(self):
        state = "On" if self.enabled else "Off"
        audio = fitText(self.audioName or "No audio service selected", 54)
        return [
            "Vidio: %s (%s)" % (state, ENGINE.state),
            "Audio source: %s" % audio,
            "Video delay: %.1f seconds  < >" % (self.delayTenths / 10.0),
        ]

    def refresh(self):
        try:
            selected = self["list"].getSelectedIndex()
        except Exception:
            selected = 0
        self["list"].setList(self.menuItems())
        try:
            self["list"].moveToIndex(selected)
        except Exception:
            pass
        status = ENGINE.status if ENGINE.state != ENGINE.STOPPED else self.readyStatus()
        self["status"].setText(fitText(status, 145))

    def readyStatus(self):
        if not fileExists(FFMPEG):
            return "ffmpeg was not found at %s." % FFMPEG
        if not self.audioRef:
            return "Select a second DVB service for replacement audio."
        return "Ready. Vidio will remux current video with the selected audio."

    def selectedIndex(self):
        try:
            return self["list"].getSelectedIndex()
        except Exception:
            return 0

    def ok(self):
        index = self.selectedIndex()
        if index == 0:
            self.enabled = not self.enabled
            if not self.enabled and ENGINE.isActive():
                ENGINE.stop(restore=True)
            self.refresh()
        elif index == 1:
            self.session.openWithCallback(self.audioSelected, VidioServiceBrowser)
        elif index == 2:
            self.delayUp()

    def audioSelected(self, selection=None):
        if not selection:
            return
        try:
            self.audioName, self.audioRef = selection
        except Exception:
            return
        self.audioName = toText(self.audioName)
        self.audioRef = toText(self.audioRef)
        self.refresh()

    def delayDown(self):
        if self.selectedIndex() == 2 and self.delayTenths > 0:
            self.delayTenths -= 1
            self.refresh()

    def delayUp(self):
        if self.selectedIndex() == 2 and self.delayTenths < 300:
            self.delayTenths += 1
            self.refresh()

    def save(self):
        config.plugins.vidio.enabled.value = bool(self.enabled)
        config.plugins.vidio.audio_name.value = self.audioName
        config.plugins.vidio.audio_ref.value = self.audioRef
        config.plugins.vidio.video_delay_tenths.value = int(self.delayTenths)
        config.plugins.vidio.save()
        configfile.save()
        if not self.enabled:
            ENGINE.stop(restore=True)
            return
        if not self.audioRef:
            self.session.open(MessageBox, "Select an audio service first.", MessageBox.TYPE_INFO, timeout=5)
            return
        if ENGINE.isActive():
            self.videoRef = ENGINE.sourceVideoRef
            self.videoName = ENGINE.sourceVideoName
        else:
            self.videoRef = currentServiceReference(self.session)
            try:
                self.videoName = serviceName(eServiceReference(self.videoRef))
            except Exception:
                self.videoName = "current service"
        ENGINE.start(
            self.session,
            self.videoRef,
            self.videoName,
            self.audioRef,
            self.audioName,
            self.delayTenths,
        )

    def engineUpdate(self, kind, message):
        if kind == "error":
            self.enabled = False
        else:
            self.enabled = ENGINE.isActive()
        self.refresh()
        if kind == "error":
            self.session.open(MessageBox, message, MessageBox.TYPE_ERROR, timeout=10)

    def cleanup(self):
        ENGINE.removeListener(self.engineUpdate)


def openVidioFromInfoBar(infoBar):
    try:
        infoBar.session.open(VidioScreen)
    except Exception:
        pass


def installInfoBarAction():
    try:
        from Screens.InfoBar import InfoBar
    except Exception:
        return

    def addActionMap(instance):
        try:
            instance["VidioActions"] = ActionMap(
                ["VidioActions"],
                {"openVidio": lambda: openVidioFromInfoBar(instance)},
                -1,
            )
        except Exception:
            pass

    if not getattr(InfoBar, "_vidioPatched", False):
        originalInit = InfoBar.__init__

        def patchedInit(self, *args, **kwargs):
            originalInit(self, *args, **kwargs)
            addActionMap(self)

        InfoBar.__init__ = patchedInit
        InfoBar._vidioPatched = True
    instance = getattr(InfoBar, "instance", None)
    if instance is not None:
        addActionMap(instance)


def loadVidioKeymap():
    global KEYMAP_LOADED
    if KEYMAP_LOADED or not fileExists(KEYMAP_FILE):
        return
    try:
        import keymapparser
        keymapparser.readKeymap(KEYMAP_FILE)
        KEYMAP_LOADED = True
    except Exception:
        pass


def openVidio(session, **kwargs):
    session.open(VidioScreen)


def autostart(reason, **kwargs):
    if reason == 0:
        killPreviousFfmpeg()
        loadVidioKeymap()
        installInfoBarAction()
    elif reason == 1:
        ENGINE.shutdown()
        killPreviousFfmpeg()


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name=PLUGIN_NAME,
            description="Play current video with audio from another DVB service",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            fnc=openVidio,
            icon="plugin.png",
        ),
        PluginDescriptor(
            name=PLUGIN_NAME,
            description="Vidio startup cleanup",
            where=PluginDescriptor.WHERE_AUTOSTART,
            fnc=autostart,
        ),
    ]
