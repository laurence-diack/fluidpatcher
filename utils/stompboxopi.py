"""
Copyright (c) 2020 Bill Peterson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

"""
Description: python interface for a raspberry pi with two gpio buttons and a 16x2 character LCD
"""


# adjust timings below as needed/desired
POLL_TIME = 0.01
HOLD_TIME = 1.0
LONG_TIME = 3.0
MENU_TIMEOUT = 5.0
BLINK_TIME = 0.1
SCROLL_TIME = 0.4


import time
import ssd1306
import OPi.GPIO as GPIO
from encoder import Encoder
from .hw_overlay import *

if ACTIVE_HIGH:
    ACTIVE = GPIO.HIGH
else:
    ACTIVE = GPIO.LOW
STATE_NONE = 0
STATE_DOWN = 1
STATE_TAP = 2
STATE_HOLD = 3
STATE_HELD = 4
STATE_LONG = 5
STATE_LONGER = 6

CHR_BSP = 0
CHR_ENT = 1
INPCHARS = " abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.\/" + chr(CHR_BSP) + chr(CHR_ENT)
PRNCHARS = ' !"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~' + chr(CHR_BSP) + chr(CHR_ENT)

class StompBox():

    def enc_left(scale_position):
        print('Encoder turned left')

    def enc_right(scale_position):
        print('Encoder turned right')

    def enc_btn(scale_position):
        print('Encoder button pressed')

    def __init__(self):

        # initialize LCD
        self.LCD = RPLCD.CharLCD(pin_rs=LCD_RS,
                            pin_e=LCD_EN,
                            pin_rw=None,
                            pins_data=[LCD_D4, LCD_D5, LCD_D6, LCD_D7],
                            numbering_mode=GPIO.BCM,
                            cols=16, rows=2,
                            compat_mode=True)
        self.LCD.create_char(CHR_BSP,[0,3,5,9,5,3,0,0])
        self.LCD.create_char(CHR_ENT,[0,1,5,9,31,8,4,0])
        self.lcd_clear()
        self.encoder = Encoder(CLK=1, DT=2, SW=3)
        self.encoder.setup(dec_callback=self.enc_left, inc_callback=self.enc_right, sw_callback=self.enc_btn)

    def lcd_clear(self):
        self.LCD.clear()
        self.scrollmsg = ''
            
    def lcd_write(self, text, row=0, col=0):
        if len(text) > 16:
            if self.scrollmsg:
                self.LCD.cursor_pos = (row, 0)
                if self.scrollpos < 0:
                    self.LCD.write_string("%-16s" % self.scrollmsg[:16])
                elif self.scrollpos < (len(self.scrollmsg) - 16):
                    self.LCD.write_string("%-16s" % self.scrollmsg[self.scrollpos:self.scrollpos+16])                    
                elif self.scrollpos < (len(self.scrollmsg) - 14):
                    self.LCD.write_string("%-16s" % self.scrollmsg[-16:])
                else:
                    self.scrollpos = -4            
            else:
                self.scrollmsg = text
                self.scrollrow = row
                self.scrollpos = -4
                self.lastscroll = time.time()
                self.LCD.cursor_pos = (row, 0)
                self.LCD.write_string("%-16s" % text[:16])
        else:
            if self.scrollmsg and row == self.scrollrow:
                self.scrollmsg = ''
            self.LCD.cursor_pos = (row, col)
            self.LCD.write_string(text)
                
            
    def lcd_blink(self, text, row=0, n=3):
        while n != 0:
            self.lcd_write(' '*16, row)
            time.sleep(BLINK_TIME)
            self.lcd_write("%-16s" % text, row)
            time.sleep(BLINK_TIME)
            n -= 1
            
    def choose_opt(self, opts, row=0, timeout=MENU_TIMEOUT, passlong=False):
        """
        has the user choose from a list of choices in :opts
        returns the index of the choice
        or -1 if the user backed out or time expired
        passlong: pass STATE_LONG through to calling loop
        """
        i=0
        while True:
            self.lcd_write(' '*16, row)
            self.lcd_write(opts[i], row)
            tstop = time.time() + timeout
            while True:
                if timeout and time.time() > tstop:
                    self.lcd_write(' '*16, row)
                    return -1
                self.update()
                if sum(self.state.values()) == STATE_NONE:
                    continue
                elif self.state[BTN_R] == STATE_TAP:
                    i=(i+1)%len(opts)
                    break
                elif self.state[BTN_L] == STATE_TAP:
                    i=(i-1)%len(opts)
                    break
                elif self.state[BTN_R] == STATE_HOLD:
                    self.lcd_blink(opts[i], row)
                    return i
                elif self.state[BTN_L] == STATE_HOLD:
                    self.lcd_write(' '*16, row)
                    return -1
                elif STATE_LONG in self.state.values() and passlong:
                    for b in self.state:
                        if self.state[b] == STATE_LONG:
                            self.state[b] = STATE_HELD
                    return -1

    def choose_val(self, val, inc, minval, maxval, format="%16s"):
        """
        lets the user change a numeric parameter
        returns the user's choice on timeout
        """
        while True:
            self.lcd_write('%16s' % (format % val), 1)
            tstop = time.time() + MENU_TIMEOUT
            while time.time() < tstop:
                self.update()
                if sum(self.state.values()) == STATE_NONE:
                    continue
                if self.state[BTN_R] > STATE_DOWN:
                    val = min(val + inc, maxval)
                elif self.state[BTN_L] > STATE_DOWN:
                    val = max(val - inc, minval)
                break
            else:
                return val

    def char_input(self, text='', row=1, timeout=MENU_TIMEOUT, charset=INPCHARS):
        """
        a way of letting the user enter a text string with two buttons
        text: the initial value of the text
        user taps buttons to choose character, holds buttons to move
         cursor right or left
        when cursor is at end of input, user can tap to
         delete or newline character
        newline returns text
        timeout returns empty string
        """
        i = len(text)
        char = len(charset) - 1
        self.LCD.cursor_mode = 'blink'
        while True:
            if i < len(text):
                char = charset.find(text[i])
            lpos = max(i - 15, 0)
            self.lcd_write("%-16s" % text[lpos:lpos + 16], row)
            if char > -1:
                self.lcd_write(charset[char], row, min(i, 15))
            self.LCD.cursor_pos = (row, min(i, 15))
            tstop = time.time() + timeout
            while time.time() < tstop:
                self.update()
                if sum(self.state.values()) == STATE_NONE:
                    continue
                elif STATE_TAP in self.state.values():
                    if i==len(text):
                        if self.state[BTN_R] == STATE_TAP:
                            char = (char + 1) % len(charset)
                        else:
                            char = (char - 1) % len(charset)
                    else:
                        if self.state[BTN_R] == STATE_TAP:
                            char = (char + 1) % (len(charset) - 2)
                        else:
                            char = (char - 1) % (len(charset) - 2)
                    if char < (len(charset) - 2):
                        text = text[0:i] + charset[char] + text[i+1:]
                    break
                elif self.state[BTN_R] >= STATE_HOLD:
                    if self.state[BTN_R] == STATE_HELD: continue
                    if char == (len(charset) - 1):
                        if self.state[BTN_R] != STATE_HOLD: continue
                        self.LCD.cursor_mode = 'hide'
                        self.lcd_blink(text.strip()[0:16], row)
                        return text.strip()
                    if self.state[BTN_R] > STATE_HELD: time.sleep(BLINK_TIME)
                    i = min(i + 1, len(text))
                    if i == len(text):
                        char = len(charset) - 1
                    break
                elif self.state[BTN_L] >= STATE_HOLD:
                    if self.state[BTN_L] == STATE_HELD: continue
                    if char == (len(charset) - 2):
                        text = text[0:max(0, i - 1)] + text[i:]
                    if self.state[BTN_L] > STATE_HELD: time.sleep(BLINK_TIME)
                    i = max(i - 1, 0)
                    break
            else:
                self.LCD.cursor_mode = 'hide'
                return ''

