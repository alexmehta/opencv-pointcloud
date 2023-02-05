import pyrealsense2 as rs
import pygame.midi
import pygame
import json
import sys

from scripts.drawnotes import NoteDrawer
from scripts.noteplayer import NotePlayer
from scripts.downsampled import GenerateDownsampled
from scripts.objectdownsampled import GenerateObjectDownsampled
from scripts.get_soundindex import get_soundindex
from scripts.get_boundingboxes import get_boundingboxes
from scripts.settingsgui import SettingsGUI
from scripts.yolo import Yolo

pygame.init()
pygame.midi.init()
pygame.font.init()
pygame.mixer.init()

my_font = pygame.font.SysFont('Arial', 30)

pipeline = rs.pipeline()
config = rs.config()

resx = 640
resy = 480


config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 30)
pc = rs.pointcloud()
pipeline.start(config)


soundsettings = None
soundfiles = {}

guisettings = json.load(open("./settings/guisettings.json"))

def loadsoundsettings():
    global soundsettings
    soundsettings = json.load(open("./settings/soundsettings.json"))

    if soundsettings["speakgrid"]:
        for classname in soundsettings["classes"]:
            soundfiles[classname] = pygame.mixer.Sound("./sounds/"+classname+".mp3")
loadsoundsettings()



class Model:

    def __init__(self):

        self.ticks = 0

        self.yolo_reader = Yolo()
        self.endsoundtick = 0
        self.soundtick= 0
        self.soundpoint = None
        self.ticklimiter = 0
        self.lastnote = None
        self.repeated = False

        self.xskip = 40
        self.yskip = 40

        self.sx = int(resx / self.xskip)
        self.sy = int(resy / self.yskip)

        self.generate_downsampled = GenerateDownsampled(self.xskip, self.yskip, resx, resy, soundsettings)
        self.generate_object_downsampled = GenerateObjectDownsampled(self.xskip, self.yskip, resx, resy)
        self.note_drawer = NoteDrawer(pygame, surface, 320, 240, self.sx, self.sy, my_font)
        self.note_player = NotePlayer(pygame)
        self.settings_gui = SettingsGUI(pygame, surface, soundsettings, guisettings, my_font)


    def draw(self):

        checkquit()

        if(self.lastnote != None): self.note_player.offnote(self.lastnote, 0)

        if(self.ticks % soundsettings["setpointinterval"] == 0 or pygame.key.get_pressed()[pygame.K_SPACE]):

            loadsoundsettings()

            self.ticklimiter = 0
            self.soundtick= 0
            if(not soundsettings["notegrid"]): self.soundtick = 99999
            self.voicetick = 0
            if(not soundsettings["speakgrid"]): self.voicetick = 99999
            self.ticks = 0
            self.soundpoint = (0, 0)
            self.endsoundtick = 0
            self.skipcol = False;

            self.downsampled = []
            self.downsampledmap = []

            self.objectdownsampled = []
            self.objectdownsampledmap = []

            frames = pipeline.wait_for_frames()
            self.depth_frame = frames.get_depth_frame()
            self.color_frame = frames.get_color_frame()
            self.downsampled, self.downsampledmap = self.generate_downsampled.generate(self.depth_frame, soundsettings["checkrange"], soundsettings["checkskip"])

            if(soundsettings["speakgrid"]):
                self.boundingboxes = get_boundingboxes(self.yolo_reader,self.color_frame);
                self.objectdownsampled, self.objectdownsampledmap = self.generate_object_downsampled.generate(self.boundingboxes)

            self.note_drawer.convert_image(self.color_frame, 320, 240)


        if( (self.ticks % soundsettings["setpointinterval"]) % soundsettings["soundtickinterval"] == 0
           and self.soundtick < len(self.downsampled)
             and
        self.ticks % soundsettings["setpointinterval"] > self.ticklimiter):

            soundindex = get_soundindex(self.downsampled[self.soundtick], soundsettings)

            y = self.soundtick % self.sy
            x = int(self.soundtick / self.sy)

            self.soundpoint = (x, y)

            pan = x / ( self.sx - 1)
            pan = int(pan * 128)

            if(self.lastnote != None):
                self.note_player.offnote(self.lastnote, 0)

            if(soundindex != None):

                pitch = soundsettings["startnote"] + soundindex * soundsettings["deltanote"]
                volume = soundsettings["startvolume"] + soundindex * soundsettings["deltavolume"]

                self.note_player.playnote( pitch, volume, pan)

                self.lastnote = pitch
                self.repeated = False

            elif(soundindex == None):

                self.note_player.drum(60, 50, pan)
                self.repeated = False

            self.soundtick += 1

            if(self.soundtick == len(self.downsampled)):
                self.endsoundtick = self.ticks % soundsettings["setpointinterval"]

            dorepeat = int(self.soundtick / self.sy) > int( (self.soundtick-1) / self.sy)

            if dorepeat and self.soundtick > 0:
                self.ticklimiter = self.ticks % soundsettings["setpointinterval"] + soundsettings["notecolumndelay"]

        if(self.soundtick >= len(self.downsampled) and
           (self.ticks % soundsettings["setpointinterval"]) % soundsettings["speakingtickinterval"] == 0 and
           self.voicetick < len(self.objectdownsampled) and
           self.ticks % soundsettings["setpointinterval"] > self.endsoundtick + soundsettings["speakingaftergriddelay"] and
           self.ticks % soundsettings["setpointinterval"] > self.ticklimiter):

            self.soundtick  = 99999

            y = self.voicetick % self.sy
            x = int(self.voicetick / self.sy)

            pan = x / ( self.sx - 1)
            pan = int(pan * 128)

            self.soundpoint = (x, y)


            if int(self.voicetick / self.sy) > int( (self.voicetick-1) / self.sy):
                self.skipcol = True;
                for i in range(self.voicetick, self.voicetick + self.sy):
                    if self.voicetick >= len(self.objectdownsampled):
                        break

                    if self.objectdownsampled[i] != 0:
                        self.skipcol = False;

            if self.objectdownsampled[self.voicetick] != 0:

                sound = soundfiles[self.objectdownsampled[self.voicetick]]
                sound.play()
                self.repeated = False
                self.ticklimiter = self.ticks % soundsettings["setpointinterval"] + soundsettings["speakingdelay"]

                self.skipcol = True;

                for i in range(self.voicetick, int( (self.voicetick+1) / self.sy) * self.sy - 1):
                    if self.voicetick >= len(self.objectdownsampled):
                        break

                    if self.objectdownsampled[i] != 0:
                        self.skipcol = False;

            else:
                self.note_player.drum(60, 50, pan)
                self.repeated = False

            self.voicetick += 1

            if self.skipcol:
                self.voicetick = ( int(self.voicetick / self.sy) + 1 ) * self.sy

            dorepeat = int(self.voicetick / self.sy) > int( (self.voicetick-1) / self.sy)

            if dorepeat and self.voicetick > 0:
                if self.ticklimiter < self.ticks % soundsettings["setpointinterval"]:
                    self.ticklimiter = self.ticks % soundsettings["setpointinterval"] + soundsettings["speakingcolumndelay"]



        if self.soundtick <= len(self.downsampled):
            self.note_drawer.draw_notes(self.downsampledmap, soundsettings["maxdistance"], soundsettings["mindistance"], 0, 255, 100, 80)
        else:
            self.note_drawer.draw_objects(self.objectdownsampledmap, 100, 80)

        self.note_drawer.draw_image(440, 80)

        if(soundsettings["speakgrid"]):
            self.note_drawer.draw_bounding_boxes(self.boundingboxes, 440, 80, resx, resy);

        self.note_drawer.draw_soundpoint(self.soundpoint, 100, 80)

        self.settings_gui.run();

        self.ticks += 1

clock = pygame.time.Clock()
surface = pygame.display.set_mode((900,600))
model = Model()


def render_text(string, fontsize, pos, col):
    text_surface = my_font.render(string, False, col)

    w = text_surface.get_width() * (fontsize / text_surface.get_height())

    text_surface = pygame.transform.scale(text_surface, (int(w), int(fontsize)) )

    surface.blit(text_surface, pos)

def checkquit():

    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return True
        elif event.type == pygame.QUIT:
            return True


while True:
    clock.tick(60)
    surface.fill((0,0,0))

    posy = 330;
    fontsize = 20;

    render_text("FPS: " + str(int(clock.get_fps())), fontsize, (100,posy), (255,255,255))
    render_text("press space to go to next frame", fontsize, (100,posy + 1.1*fontsize), (255,255,255))
    objectkeys = list(soundsettings.keys())
    render_text("Interval: " + str(model.ticks) + "/" + str(soundsettings["setpointinterval"]), fontsize, (100,posy + 2*1.1*fontsize), (255,255,255))

    model.draw()
    pygame.display.update()

    if(checkquit()):
        break
sys.exit(1)
