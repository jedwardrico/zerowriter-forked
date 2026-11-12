#
# ZeroWriter
#
# This code is open-source. Feel free to modify and redistribute as you want.
# Participate on reddit in r/zerowriter if you want.
#
# Using the epd5in76 library (Good Display GDEH0576T81, 920x680, SSD2677)
#
# a python e-typewriter using eink and a USB keyboard
# this program outputs directly to the SPI eink screen, and is driven by a
# raspberry pi zero (or any pi). technically, it operates headless as the OS has no
# access to the SPI screen. it handles keyboard input directly via keyboard library.
#
# currently ONLY supports the GDEH0576T81 5.76" panel (see WIRING.md)
#

import time
import keyboard
import keymaps
from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd5in76
import textwrap
import subprocess
import signal
import os
import threading
import functools
import re
import math
from pathlib import Path


# Initialize the e-Paper display
# clear refreshes whole screen, should be done on slow init()
epd = epd5in76.EPD()
epd.init()
epd.Clear()

#Initialize display-related variables)
display_image = Image.new('1', (epd.width,epd.height), 255)
display_draw = ImageDraw.Draw(display_image)

#Display settings like font size, spacing, etc.
display_start_line = 0
SCREEN_W = epd.width
SCREEN_H = epd.height
font24 = ImageFont.truetype('Courier Prime.ttf', 28)
font_status = ImageFont.truetype('Courier Prime.ttf', 20)
font_small = ImageFont.truetype('Courier Prime.ttf', 18)
font_big = ImageFont.truetype('Courier Prime.ttf', 32)
font_name = ImageFont.truetype('Courier Prime.ttf', 26)
textWidth=16
linespacing = 36
chars_per_line = 52
lines_on_screen = 14  # lines of text shown above the input line
TEXT_TOP = 4
INPUT_Y = TEXT_TOP + lines_on_screen * linespacing  # top of the input line area
PANEL_Y = INPUT_Y + 40    # top of the bottom panel (page bar, divider, stats, file name)
# partial updates leave ghosting; after this many, the next full redraw
# (new line / scroll) also does a full-screen refresh. Tune to taste.
FULL_REFRESH_AFTER = int(os.environ.get('ZW_FULL_REFRESH_AFTER', 60))
# Typing only redraws the bottom INPUT_STRIP_ROWS lines of the screen (the
# input line plus the lines just above it). A strip updates much faster than
# the whole screen: ~315 ms for 240 rows vs ~800 ms full-frame. Fewer rows are
# faster but dimmer (120 is unreadable). Set to 0 to always update the whole
# screen. Try e.g. ZW_STRIP_ROWS=300 for more contrast.
INPUT_STRIP_ROWS = int(os.environ.get('ZW_STRIP_ROWS', 240))
INPUT_STRIP_REPEAT = int(os.environ.get('ZW_STRIP_REPEAT', 1))
last_display_update = time.time()
# (input_content, cursor_position) as last drawn on the screen; None = the
# input line is not currently drawn. Used to redraw whenever the text has
# changed, including keys typed while a previous update was still running.
last_input_rendered = None

#display related
needs_display_update = True
needs_input_update = True
updating_input_area = False
input_catchup = False
display_catchup = False
display_updating = False
shift_active = False
control_active = False
exit_cleanup = False
console_message = ""
scrollindex=1


# Initialize cursor position
cursor_position = 0

# Initialize text matrix (size of text file)
max_lines = 100  # Maximum number of lines, adjust as needed
max_chars_per_line = chars_per_line  # Maximum characters per line, adjust as needed
text_content=""
temp_content=""
input_content=""
previous_lines = []
typing_last_time = time.time()  # Timestamp of last key press

#file directory setup
# data/cache.txt      working copy of the current text (restored on startup)
# data/current_doc.txt name of the current document ("" = not saved yet)
# data/documents/*.txt saved documents
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DOCS_DIR = os.path.join(DATA_DIR, 'documents')
file_path = os.path.join(DATA_DIR, 'cache.txt')
current_doc_path = os.path.join(DATA_DIR, 'current_doc.txt')
os.makedirs(DOCS_DIR, exist_ok=True)

current_doc = None   # document name without ".txt", or None if never saved
mode = 'edit'        # 'edit' | 'prompt' (typing a file name) | 'browse' (file list)
prompt_label = ""
prompt_text = ""
prompt_action = None  # 'save' or 'rename'
browse_files = []
browse_index = 0
browse_confirm_delete = False
browse_info = {}  # name -> (modified date text, word count), filled when the list opens
MAX_NAME_LEN = 32

def load_previous_lines(file_path):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            return [line.rstrip('\n') for line in lines]
    except FileNotFoundError:
        return []

def save_previous_lines(file_path, lines):
    # write to a temp file then rename, so a power cut can't leave a half file
    tmp = file_path + '.tmp'
    with open(tmp, 'w') as file:
        for line in lines:
            file.write(line + '\n')
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp, file_path)

def sanitize_name(name):
    name = re.sub(r'[^A-Za-z0-9 _.-]', '_', name).strip().lstrip('.')
    if name.lower().endswith('.txt'):
        name = name[:-4]
    return name.strip()[:MAX_NAME_LEN]

def doc_path(name):
    return os.path.join(DOCS_DIR, name + '.txt')

def list_documents():
    """Saved document names, most recently modified first."""
    names = [f[:-4] for f in os.listdir(DOCS_DIR) if f.endswith('.txt')]
    names.sort(key=lambda n: os.path.getmtime(doc_path(n)), reverse=True)
    return names

def doc_info(name):
    """(date text, word count) for the file list."""
    path = doc_path(name)
    date = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path)))
    try:
        with open(path) as f:
            words = len(f.read().split())
    except OSError:
        words = 0
    return date, words

def doc_lines():
    """The whole document as lines, including the line being typed."""
    return previous_lines + ([input_content] if input_content else [])

def save_current_doc():
    """Write the working copy, and the named document if there is one."""
    save_previous_lines(file_path, previous_lines)
    if current_doc:
        save_previous_lines(doc_path(current_doc), doc_lines())

def remember_current_doc():
    with open(current_doc_path, 'w') as f:
        f.write(current_doc or "")

def load_current_doc_name():
    try:
        with open(current_doc_path) as f:
            name = sanitize_name(f.read())
    except FileNotFoundError:
        return None
    return name if name and os.path.exists(doc_path(name)) else None

def word_count():
    return sum(len(l.split()) for l in previous_lines) + len(input_content.split())

def char_count():
    # +1 per finished line for the space/newline at the wrap point
    return sum(len(l) + 1 for l in previous_lines) + len(input_content)

def total_pages():
    return max(1, math.ceil(len(previous_lines) / lines_on_screen))

def current_page():
    return max(1, total_pages() - scrollindex + 1)

session_start = time.time()  # when this writing session began (program start, or last new/open)

def reset_session():
    """Restart the session clock (new file, or a saved file opened)."""
    global session_start
    session_start = time.time()

def session_time():
    """Time since the session started, as HH:MM:SS."""
    secs = int(time.time() - session_start)
    return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"

# The keyboard callbacks run on their own thread and call update_display(),
# while the main loop calls update_input_area(). Drawing into display_image and
# sending it to the panel must not overlap, so both run under this lock.
display_lock = threading.RLock()

def with_display_lock(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with display_lock:
            return fn(*args, **kwargs)
    return wrapper

def draw_centered(cx, y, text, font):
    display_draw.text((cx - font.getlength(text) / 2, y), text, font=font, fill=0)

def draw_status():
    """Bottom panel: page bar, divider, session time / words / characters, file name."""
    display_draw.rectangle((0, PANEL_Y, SCREEN_W, SCREEN_H), fill=255)
    page, pages = current_page(), total_pages()

    # page progress bar: "Pg 2 ------[=]------ of 5"
    row_y = PANEL_Y + 2
    left, right = f"Pg {page}", f"of {pages}"
    display_draw.text((10, row_y), left, font=font_small, fill=0)
    display_draw.text((SCREEN_W - 10 - font_small.getlength(right), row_y), right, font=font_small, fill=0)
    x0, x1, mid = 90, SCREEN_W - 90, row_y + 10
    display_draw.line((x0, mid, x1, mid), fill=0)
    marker_w = 40
    frac = (page - 1) / (pages - 1) if pages > 1 else 0
    mx = x0 + (x1 - x0 - marker_w) * frac
    display_draw.rectangle((mx, mid - 2, mx + marker_w, mid + 2), fill=0)

    # the divider between the text and the stats
    div_y = PANEL_Y + 28
    display_draw.line((10, div_y, SCREEN_W - 10, div_y), fill=0, width=2)

    # stats row
    words = word_count()
    val_y, label_y = div_y + 8, div_y + 44
    left_x, right_x = SCREEN_W * 0.17, SCREEN_W * 0.83
    draw_centered(left_x, val_y + 4, session_time(), font_status)
    draw_centered(left_x, label_y, "Session Time", font_small)
    draw_centered(SCREEN_W / 2, val_y, f"Words: {words:,}", font_big)
    draw_centered(right_x, val_y + 4, f"{char_count():,}", font_status)
    draw_centered(right_x, label_y, "Characters", font_small)

    # file name
    name = current_doc if current_doc else "untitled"
    if len(name) > MAX_NAME_LEN:
        name = name[:MAX_NAME_LEN - 1] + "~"
    draw_centered(SCREEN_W / 2, label_y + 20, name, font_name)

def draw_browser():
    visible = lines_on_screen - 2
    draw_centered(SCREEN_W / 2, TEXT_TOP, "Up/Down: choose  Shift: page  Enter: open  Del: delete  Esc: cancel", font_small)
    if not browse_files:
        display_draw.text((10, linespacing * 2), "(no saved files yet - Ctrl+S to save)", font=font24, fill=0)
        return
    top = (browse_index // visible) * visible  # window moves a page at a time
    y = TEXT_TOP + linespacing
    for i in range(top, min(top + visible, len(browse_files))):
        name = browse_files[i]
        marker = ">" if i == browse_index else " "
        if i == browse_index and browse_confirm_delete:
            display_draw.text((10, y), f"{marker} {name}   delete? (y/n)", font=font24, fill=0)
        else:
            display_draw.text((10, y), f"{marker} {name}", font=font24, fill=0)
            date, words = browse_info.get(name, ("", 0))
            wtext = f"{words:,} word{'' if words == 1 else 's'}"
            display_draw.text((580, y + 5), date, font=font_status, fill=0)
            display_draw.text((SCREEN_W - 10 - font_status.getlength(wtext), y + 5), wtext, font=font_status, fill=0)
        y += linespacing
    # page indicator for long lists
    if len(browse_files) > visible:
        pg = f"{browse_index // visible + 1}/{math.ceil(len(browse_files) / visible)}"
        display_draw.text((SCREEN_W - 10 - font_small.getlength(pg), INPUT_Y + 8), pg, font=font_small, fill=0)

def current_input():
    """(text, cursor) to show on the input line for the current mode."""
    if mode == 'prompt':
        return prompt_label + prompt_text, len(prompt_label) + len(prompt_text)
    return input_content, cursor_position

@with_display_lock
def update_display(force_full=False):
    global last_display_update
    global needs_display_update
    global cursor_index
    global previous_lines
    global display_updating
    global updating_input_area
    global console_message
    global current_line
    global scrollindex
    global last_input_rendered
    
    last_input_rendered = None  # the clear below also erases the input line
    # Clear the main display area -- also clears input line
    display_draw.rectangle((0, 0, SCREEN_W, SCREEN_H), fill=255)
    
    # Display the previous lines
    y_position = INPUT_Y - linespacing  # leaves room for cursor input

    #Make a temp array from previous_lines. And then reverse it and display as usual.
    current_line=max(0,len(previous_lines)-lines_on_screen*scrollindex)
    temp=previous_lines[current_line:current_line+lines_on_screen]
    #print(temp)# to debug if you change the font parameters (size, chars per line, etc)

    if mode == 'browse':
        draw_browser()
    else:
        for line in reversed(temp[-lines_on_screen:]):
           display_draw.text((10, y_position), line[:max_chars_per_line], font=font24, fill=0)
           y_position -= linespacing

    if mode == 'prompt':
        text, cursor = current_input()
        display_draw.text((10, INPUT_Y), text[:cursor] + "|" + text[cursor:], font=font24, fill=0)

    draw_status()

    #Display Console Message
    if console_message != "":
        display_draw.rectangle((SCREEN_W - 160, INPUT_Y, SCREEN_W, SCREEN_H), fill=255)
        display_draw.text((SCREEN_W - 160, INPUT_Y), console_message, font=font24, fill=0)
        console_message = ""
    
    #generate display buffer for display
    partial_buffer = epd.getbuffer(display_image)
    if force_full or epd.partial_count >= FULL_REFRESH_AFTER:
        # clear ghosting with a full refresh, then go back to partial mode
        epd.init()
        epd.display(partial_buffer)
        epd.init_Partial()
    else:
        epd.display(partial_buffer)

    last_display_update = time.time()
    display_catchup = True
    display_updating= False
    needs_display_update = False

@with_display_lock
def update_input_area(): #this updates the input area of the typewriter (active line)
    global last_display_update
    global needs_display_update
    global cursor_index
    global needs_input_update
    global updating_input_area
    global last_input_rendered

    # snapshot the text now; keys typed while this update runs will make the
    # snapshot differ from the live state, so the main loop redraws again
    content, cursor_index = current_input()
    last_input_rendered = (content, cursor_index)
    display_draw.rectangle((0, INPUT_Y, SCREEN_W, SCREEN_H), fill=255)  # Clear input area
    
    #add cursor
    temp_content = content[:cursor_index] + "|" + content[cursor_index:]
    
    #draw input line text
    display_draw.text((10, INPUT_Y), str(temp_content), font=font24, fill=0)
    draw_status()  # word count changes as you type
    
    #generate display buffer for input line
    updating_input_area = True
    partial_buffer = epd.getbuffer(display_image)
    if INPUT_STRIP_ROWS >= 120:
        epd.display_bottom_strip(partial_buffer, INPUT_STRIP_ROWS, INPUT_STRIP_REPEAT)
    else:
        epd.display(partial_buffer)
    updating_input_area = False
    
def insert_character(character):
    global cursor_position
    global input_content
    global needs_display_update
    
    cursor_index = cursor_position
    
    if cursor_index <= len(input_content):
        # Insert character in the text_content string
        input_content = input_content[:cursor_index] + character + input_content[cursor_index:]
        cursor_position += 1  # Move the cursor forward
    
    needs_input_update = True

def delete_character():
    global cursor_position
    global input_content
    global needs_display_update
    
    cursor_index = cursor_position
    
    if cursor_index > 0:
        # Remove the character at the cursor position
        input_content = input_content[:cursor_index - 1] + input_content[cursor_index:]
        cursor_position -= 1  # Move the cursor back
        needs_input_update = True

    
def set_current_doc(name):
    global current_doc
    current_doc = name
    remember_current_doc()

def archive_current_doc():
    """Save the current text before replacing it. Unnamed text gets a timestamp name."""
    global current_doc
    if current_doc:
        save_current_doc()
    elif previous_lines or input_content:
        name = "zw_" + time.strftime("%Y%m%d%H%M%S")
        save_previous_lines(doc_path(name), doc_lines())

def start_prompt(action, label, initial=""):
    global mode, prompt_action, prompt_label, prompt_text
    mode, prompt_action, prompt_label, prompt_text = 'prompt', action, label, initial
    update_display()

def start_browser():
    global mode, browse_files, browse_index, browse_confirm_delete, browse_info
    browse_files = list_documents()
    browse_info = {n: doc_info(n) for n in browse_files}
    browse_index = 0
    browse_confirm_delete = False
    if current_doc in browse_files:
        browse_index = browse_files.index(current_doc)
    mode = 'browse'
    update_display()

def end_modal(message=""):
    global mode, console_message, last_input_rendered
    mode = 'edit'
    console_message = message
    update_display()
    last_input_rendered = None

def open_document(name):
    global previous_lines, input_content, cursor_position, scrollindex
    archive_current_doc()
    previous_lines = load_previous_lines(doc_path(name))
    input_content = ""
    cursor_position = 0
    scrollindex = 1
    set_current_doc(name)
    save_previous_lines(file_path, previous_lines)
    reset_session()

def finish_prompt():
    """Enter pressed in the file-name prompt."""
    global console_message
    name = sanitize_name(prompt_text)
    if not name:
        end_modal("[Cancelled]")
        return
    if name != current_doc and os.path.exists(doc_path(name)):
        console_message = "[Name taken]"
        update_display()
        return
    old = current_doc
    set_current_doc(name)
    save_current_doc()
    if old and old != name and prompt_action == 'rename':
        try:
            os.remove(doc_path(old))
        except FileNotFoundError:
            pass
    end_modal("[Saved]")

def handle_modal_key(e):
    """Keys while typing a file name or choosing a file."""
    global prompt_text, browse_index, browse_confirm_delete, browse_files, mode
    if mode == 'prompt':
        if e.name == "enter":
            finish_prompt()
        elif e.name == "esc":
            end_modal("[Cancelled]")
        elif e.name == "backspace":
            prompt_text = prompt_text[:-1]
        elif e.name == "space":
            prompt_text += " "
        elif len(e.name) == 1 and not control_active:
            char = keymaps.shift_mapping.get(e.name, e.name) if shift_active else e.name
            if len(prompt_text) < MAX_NAME_LEN:
                prompt_text += char
        return

    # browse
    if browse_confirm_delete:
        if e.name == "y" and browse_files:
            name = browse_files.pop(browse_index)
            try:
                os.remove(doc_path(name))
            except FileNotFoundError:
                pass
            if name == current_doc:
                set_current_doc(None)  # text stays on screen, but is unsaved again
            browse_index = max(0, min(browse_index, len(browse_files) - 1))
        browse_confirm_delete = False
        update_display()
    elif e.name == "up":
        step = (lines_on_screen - 2) if shift_active else 1  # shift = a page at a time
        browse_index = max(0, browse_index - step)
        update_display()
    elif e.name == "down":
        step = (lines_on_screen - 2) if shift_active else 1
        browse_index = min(max(0, len(browse_files) - 1), browse_index + step)
        update_display()
    elif e.name == "delete" and browse_files:
        browse_confirm_delete = True
        update_display()
    elif e.name == "enter" and browse_files:
        open_document(browse_files[browse_index])
        mode = 'edit'
        console_message_set("[Opened]")
        update_display(force_full=True)
    elif e.name == "esc":
        end_modal()

def console_message_set(msg):
    global console_message
    console_message = msg

def handle_key_down(e): #keys being held, ie modifier keys
    global shift_active
    global control_active
    
    if e.name == 'shift': #if shift is released
        shift_active = True
    if e.name == 'ctrl': #if shift is released
        control_active = True
    

def handle_key_press(e):
    global cursor_position
    global typing_last_time
    global display_start_line
    global needs_display_update
    global needs_input_update
    global shift_active
    global exit_cleanup
    global input_content
    global previous_lines
    global display_updating
    global input_catchup
    global control_active
    global console_message
    global scrollindex
    
    #modifier release must always be tracked, whatever mode we are in
    if e.name == 'ctrl':
        control_active = False
    if e.name == 'shift':
        shift_active = False

    if mode != 'edit':
        handle_modal_key(e)
        return

    #save via ctrl + s (asks for a name the first time)
    if e.name== "s" and control_active:
        if current_doc:
            save_current_doc()
            console_message = "[Saved]"
            update_display()
            time.sleep(1)
            console_message = ""
            update_display()
        else:
            start_prompt('save', "Save as: ")
        return

    #rename / save as via ctrl + r
    if e.name== "r" and control_active:
        start_prompt('rename', "Rename to: ", current_doc or "")
        return

    #open a saved file via ctrl + o
    if e.name== "o" and control_active:
        start_browser()
        return

    #new file (clear) via ctrl + n
    if e.name== "n" and control_active: #ctrl+n
        archive_current_doc()

        #create a blank doc
        previous_lines.clear()
        input_content = ""
        cursor_position = 0
        scrollindex = 1
        set_current_doc(None)
        save_previous_lines(file_path, previous_lines)
        reset_session()

        console_message = f"[New]"
        update_display(force_full=True)  # clean slate: full refresh clears the old page
        time.sleep(1)
        console_message = ""
        update_display()

    if e.name== "down" or e.name== "right":
       #move scrollindex down
       scrollindex = scrollindex - 1
       if scrollindex < 1:
            scrollindex = 1
       update_display()

    if e.name== "up" or e.name== "left":
       #move scrollindex up
       scrollindex = scrollindex + 1
       if scrollindex > total_pages():
            scrollindex = total_pages()
       update_display()

    #powerdown - could add an autosleep if you want to save battery
    if e.name == "esc" and control_active: #ctrl+esc
        #run powerdown script
        display_draw.rectangle((0, 0, SCREEN_W, SCREEN_H), fill=255)  # Clear display
        msg = "ZeroWriter Powered Down."
        display_draw.text(((SCREEN_W - font24.getlength(msg)) // 2, SCREEN_H // 2), msg, font=font24, fill=0)
        partial_buffer = epd.getbuffer(display_image)
        epd.display(partial_buffer)
        time.sleep(3)
        subprocess.run(['sudo', 'poweroff', '-f'])
        
        needs_display_update = True
        needs_input_update = True
        input_catchup = True
        
        
    if e.name == "tab": 
        #just using two spaces for tab, kind of cheating, whatever.
        insert_character(" ")
        insert_character(" ")
        
        # Check if adding the character exceeds the line length limit
        if cursor_position > chars_per_line:
            previous_lines.append(input_content)                
            # Update input_content to contain the remaining characters
            input_content = ""
            needs_display_update = True #trigger a display refresh
        # Update cursor_position to the length of the remaining input_content
        cursor_position = len(input_content)
        
        needs_input_update = True
        input_catchup = True
        
    if e.name == "backspace":
        delete_character()
        needs_input_update = True
        input_catchup = True
            
    elif e.name == "space": #space bar
        insert_character(" ")
        
        # Check if adding the character exceeds the line length limit
        if cursor_position > chars_per_line:
            previous_lines.append(input_content)                
            input_content = ""
            needs_display_update = True
        # Update cursor_position to the length of the remaining input_content
        cursor_position = len(input_content)
        
        needs_input_update = True
        input_catchup = True
    
    elif e.name == "enter":
        if scrollindex>1:
            #if you were reviewing text, jump to scrollindex=1
            scrollindex = 1
            update_display()
        else:
            # Add the input to the previous_lines array
            previous_lines.append(input_content)
            input_content = "" #clears input content
            cursor_position=0
            #save the file when enter is pressed
            save_current_doc()
            needs_display_update = True
            input_catchup = True
        
    if len(e.name) == 1 and control_active == False:  # letter and number input
        
        if shift_active:
            char = keymaps.shift_mapping.get(e.name)
            input_content += char
        else:
            input_content += e.name
            
        cursor_position += 1
        needs_input_update = True

        # Check if adding the character exceeds the line length limit
        if len(input_content) > chars_per_line:
            # Find the last space character before the line length limit
            last_space = input_content.rfind(' ', 0, chars_per_line)
            if last_space <= 0:
                # No usable space (one long unbroken word): hard-break at the
                # limit. (Splitting at -1 used to append a near-copy of the
                # word as a new line on every extra keystroke.)
                sentence = input_content[:chars_per_line]
                input_content = input_content[chars_per_line:]
            else:
                sentence = input_content[:last_space]
                # Update input_content to contain the remaining characters
                input_content = input_content[last_space + 1:]
            # Append the sentence to the previous lines
            previous_lines.append(sentence)
            needs_display_update=True
            
        # Update cursor_position to the length of the remaining input_content
        cursor_position = len(input_content)                

    typing_last_time = time.time()
    input_catchup==True
    needs_input_update = True
    
def handle_interrupt(signal, frame):
    keyboard.unhook_all()
    epd.init()
    epd.Clear()
    epd.sleep()
    exit(0)

#Startup Stuff ---
keyboard.on_press(handle_key_down, suppress=False) #handles modifiers and shortcuts
keyboard.on_release(handle_key_press, suppress=True)
signal.signal(signal.SIGINT, handle_interrupt)

#init_display routine
epd.init()
epd.Clear
previous_lines = load_previous_lines(file_path)#('previous_lines.txt')
current_doc = load_current_doc_name()
epd.init_Partial()
epd.Clear
needs_display_update = True
needs_input_update = False


#mainloop
try:
    while True:
        
        if exit_cleanup:
            break
                
        if needs_display_update and not display_updating:
            update_display()
            needs_diplay_update=False
            typing_last_time = time.time()
            
        elif mode != 'browse' and scrollindex==1 and not updating_input_area and current_input() != last_input_rendered:
            #redraw the input line whenever the text differs from what is on screen.
            #(the old "within 0.5s of the last key" rule dropped letters typed during a slow update)
            update_input_area()
        time.sleep(0.02) # keeps the main loop from hogging the CPU (and starving the keyboard thread)
        
except KeyboardInterrupt:
    pass

finally:
    keyboard.unhook_all()
    epd.init()
    time.sleep(1)
    epd.Clear()
    epd.sleep()
