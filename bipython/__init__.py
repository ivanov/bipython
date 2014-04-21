#  Copyright (c) 2014, Paul Ivanov <pi@bereley.edu>
#  Distributed under the terms of the Modified BSD License.
#  The full license is in the LICENSE file distributed with this software.

"""bipython: the boldly indiscriminate Python interpreter

http://bipython.org
"""
from __future__ import absolute_import, with_statement, division
from __future__ import print_function

__author__ = 'Paul Ivanov <pi@berkeley.edu>'
__copyright__ = 'Copyright (c) 2014 Paul Ivanov'
__license__ = 'BSD'
__version__ = '0.1.3'

import sys
import os
import time
import locale
import signal
from types import ModuleType
from optparse import Option

from pygments.token import Token

from bpython import args as bpargs, repl, translations
from bpython.formatter import theme_map
from bpython.importcompletion import find_coroutine
from bpython.translations import _

from bpython.keys import urwid_key_dispatch as key_dispatch
from bpython._py3compat import PythonLexer, py3

import urwid
import inspect
from inspect import ArgSpec # we eval an ArgSpec repr, see ipython_get_argspec

try:
    #python 3
    from queue import Empty
except ImportError:
    #python 2
    from Queue import Empty

Parenthesis = Token.Punctuation.Parenthesis

try:
    import subprocess
    commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=os.path.dirname(__file__)).strip()
    __version__ += ' [' + commit + ']'
except:
    pass

version = '%s (Python %s) ' % (__version__, sys.version.split()[0])



# Urwid colors are:
# 'black', 'dark red', 'dark green', 'brown', 'dark blue',
# 'dark magenta', 'dark cyan', 'light gray', 'dark gray',
# 'light red', 'light green', 'yellow', 'light blue',
# 'light magenta', 'light cyan', 'white'
# and bpython has:
# blacK, Red, Green, Yellow, Blue, Magenta, Cyan, White, Default

COLORMAP = {
    'k': 'black',
    'r': 'dark red', # or light red?
    'g': 'dark green', # or light green?
    'y': 'yellow',
    'b': 'dark blue', # or light blue?
    'm': 'dark magenta', # or light magenta?
    'c': 'dark cyan', # or light cyan?
    'w': 'white',
    'd': 'default',
    }

# Add our keys to the urwid command_map
bipy_func = """
def get_object(name):
    attributes = name.split('.')
    obj = eval(attributes.pop(0))
    while attributes:
        #with AttrCleaner(obj):
        obj = getattr(obj, attributes.pop(0))
    return obj

def bipy_argspec(func):
    try:
        f = get_object(func)
    except (AttributeError, NameError, SyntaxError):
        return False

    if inspect.isclass(f):
        try:
            if f.__init__ is not object.__init__:
                f = f.__init__
        except AttributeError:
            return None
    return getargspec(func, f)
"""
hack_path = os.path.dirname(__file__)
with open(os.path.join(hack_path, 'inspection_standalone.py')) as f:
    bipy_func = f.read() + bipy_func



try:
    from twisted.internet import protocol
    from twisted.protocols import basic
except ImportError:
    pass
else:

    class EvalProtocol(basic.LineOnlyReceiver):

        delimiter = '\n'

        def __init__(self, myrepl):
            self.repl = myrepl

        def lineReceived(self, line):
            # HACK!
            # TODO: deal with encoding issues here...
            self.repl.main_loop.process_input(line)
            self.repl.main_loop.process_input(['enter'])


    class EvalFactory(protocol.ServerFactory):

        def __init__(self, myrepl):
            self.repl = myrepl

        def buildProtocol(self, addr):
            return EvalProtocol(self.repl)

# XXX: copy-paste eng from vim-ipython
import re
# from http://serverfault.com/questions/71285/in-centos-4-4-how-can-i-strip-escape-sequences-from-a-text-file
strip = re.compile('\x1B\[([0-9]{1,2}(;[0-9]{1,2})?)?[m|K]')

def strip_color_escapes(s):
    return strip.sub('',s)


# If Twisted is not available urwid has no TwistedEventLoop attribute.
# Code below will try to import reactor before using TwistedEventLoop.
# I assume TwistedEventLoop will be available if that import succeeds.
if urwid.VERSION < (1, 0, 0) and hasattr(urwid, 'TwistedEventLoop'):
    class TwistedEventLoop(urwid.TwistedEventLoop):

        """TwistedEventLoop modified to properly stop the reactor.

        urwid 0.9.9 and 0.9.9.1 crash the reactor on ExitMainLoop instead
        of stopping it. One obvious way this breaks is if anything used
        the reactor's thread pool: that thread pool is not shut down if
        the reactor is not stopped, which means python hangs on exit
        (joining the non-daemon threadpool threads that never exit). And
        the default resolver is the ThreadedResolver, so if we looked up
        any names we hang on exit. That is bad enough that we hack up
        urwid a bit here to exit properly.
        """

        def handle_exit(self, f):
            def wrapper(*args, **kwargs):
                try:
                    return f(*args, **kwargs)
                except urwid.ExitMainLoop:
                    # This is our change.
                    self.reactor.stop()
                except:
                    # This is the same as in urwid.
                    # We are obviously not supposed to ever hit this.
                    import sys
                    print(sys.exc_info())
                    self._exc_info = sys.exc_info()
                    self.reactor.crash()
            return wrapper
else:
    TwistedEventLoop = getattr(urwid, 'TwistedEventLoop', None)


class StatusbarEdit(urwid.Edit):
    """Wrapper around urwid.Edit used for the prompt in Statusbar.

    This class only adds a single signal that is emitted if the user presses
    Enter."""

    signals = urwid.Edit.signals + ['prompt_enter']

    def __init__(self, *args, **kwargs):
        self.single = False
        urwid.Edit.__init__(self, *args, **kwargs)

    def keypress(self, size, key):
        if self.single:
            urwid.emit_signal(self, 'prompt_enter', self, key)
        elif key == 'enter':
            urwid.emit_signal(self, 'prompt_enter', self, self.get_edit_text())
        else:
            return urwid.Edit.keypress(self, size, key)

urwid.register_signal(StatusbarEdit, 'prompt_enter')

class Statusbar(object):

    """Statusbar object, ripped off from bpython.cli.

    This class provides the status bar at the bottom of the screen.
    It has message() and prompt() methods for user interactivity, as
    well as settext() and clear() methods for changing its appearance.

    The check() method needs to be called repeatedly if the statusbar is
    going to be aware of when it should update its display after a message()
    has been called (it'll display for a couple of seconds and then disappear).

    It should be called as:
        foo = Statusbar('Initial text to display')
    or, for a blank statusbar:
        foo = Statusbar()

    The "widget" attribute is an urwid widget.
    """

    signals = ['prompt_result']

    def __init__(self, config, s=None, main_loop=None):
        self.config = config
        self.timer = None
        self.main_loop = main_loop
        self.s = s or ''

        self.text = urwid.Text(('main', self.s))
        # use wrap mode 'clip' to just cut off at the end of line
        self.text.set_wrap_mode('clip')

        self.edit = StatusbarEdit(('main', ''))
        urwid.connect_signal(self.edit, 'prompt_enter', self._on_prompt_enter)

        self.widget = urwid.Columns([self.text, self.edit])

    def _check(self, callback, userdata=None):
        """This is the method is called from the timer to reset the status bar."""
        self.timer = None
        self.settext(self.s)

    def message(self, s, n=3):
        """Display a message for a short n seconds on the statusbar and return
        it to its original state."""

        self.settext(s)
        self.timer = self.main_loop.set_alarm_in(n, self._check)

    def _reset_timer(self):
        """Reset the timer from message."""
        if self.timer is not None:
            self.main_loop.remove_alarm(self.timer)
            self.timer = None

    def prompt(self, s=None, single=False):
        """Prompt the user for some input (with the optional prompt 's'). After
        the user hit enter the signal 'prompt_result' will be emited and the
        status bar will be reset. If single is True, the first keypress will be
        returned."""

        self._reset_timer()

        self.edit.single = single
        self.edit.set_caption(('main', s or '?'))
        self.edit.set_edit_text('')
        # hide the text and display the edit widget
        if not self.edit in self.widget.widget_list:
            self.widget.widget_list.append(self.edit)
        if self.text in self.widget.widget_list:
            self.widget.widget_list.remove(self.text)
        self.widget.set_focus_column(0)

    def settext(self, s, permanent=False):
        """Set the text on the status bar to a new value. If permanent is True,
        the new value will be permanent. If that status bar is in prompt mode,
        the prompt will be aborted. """

        self._reset_timer()

        # hide the edit and display the text widget
        if self.edit in self.widget.widget_list:
            self.widget.widget_list.remove(self.edit)
        if not self.text in self.widget.widget_list:
            self.widget.widget_list.append(self.text)

        self.text.set_text(('main', s))
        if permanent:
          self.s = s

    def clear(self):
        """Clear the status bar."""
        self.settext('')

    def _on_prompt_enter(self, edit, new_text):
        """Reset the statusbar and pass the input from the prompt to the caller
        via 'prompt_result'."""
        self.settext(self.s)
        urwid.emit_signal(self, 'prompt_result', new_text)

urwid.register_signal(Statusbar, 'prompt_result')


def decoding_input_filter(keys, raw):
    """Input filter for urwid which decodes each key with the locale's
    preferred encoding.'"""
    encoding = locale.getpreferredencoding()
    converted_keys = list()
    for key in keys:
        if isinstance(key, basestring):
            converted_keys.append(key.decode(encoding))
        else:
            converted_keys.append(key)
    return converted_keys

def format_tokens(tokensource):
    for token, text in tokensource:
        if text == '\n':
            continue

        # TODO: something about inversing Parenthesis
        while token not in theme_map:
            token = token.parent
        yield (theme_map[token], text)


class BPythonEdit(urwid.Edit):

    """Customized editor *very* tightly interwoven with URWIDRepl.

    Changes include:

    - The edit text supports markup, not just the caption.
      This works by calling set_edit_markup from the change event
      as well as whenever markup changes while text does not.

    - The widget can be made readonly, which currently just means
      it is no longer selectable and stops drawing the cursor.

      This is currently a one-way operation, but that is just because
      I only need and test the readwrite->readonly transition.

    - move_cursor_to_coords is ignored
      (except for internal calls from keypress or mouse_event).

    - arrow up/down are ignored.

    - an "edit-pos-changed" signal is emitted when edit_pos changes.
    """

    signals = ['edit-pos-changed']

    def __init__(self, config, *args, **kwargs):
        self._bpy_text = ''
        self._bpy_attr = []
        self._bpy_selectable = True
        self._bpy_may_move_cursor = False
        self.config = config
        self.tab_length = config.tab_length
        urwid.Edit.__init__(self, *args, **kwargs)

    def set_edit_pos(self, pos):
        urwid.Edit.set_edit_pos(self, pos)
        self._emit("edit-pos-changed", self.edit_pos)

    def get_edit_pos(self):
        return self._edit_pos

    edit_pos = property(get_edit_pos, set_edit_pos)

    def make_readonly(self):
        self._bpy_selectable = False
        # This is necessary to prevent the listbox we are in getting
        # fresh cursor coords of None from get_cursor_coords
        # immediately after we go readonly and then getting a cached
        # canvas that still has the cursor set. It spots that
        # inconsistency and raises.
        self._invalidate()

    def set_edit_markup(self, markup):
        """Call this when markup changes but the underlying text does not.

        You should arrange for this to be called from the 'change' signal.
        """
        if markup:
            self._bpy_text, self._bpy_attr = urwid.decompose_tagmarkup(markup)
        else:
            # decompose_tagmarkup in some urwids fails on the empty list
            self._bpy_text, self._bpy_attr = '', []
        # This is redundant when we're called off the 'change' signal.
        # I'm assuming this is cheap, making that ok.
        self._invalidate()

    def get_text(self):
        return self._caption + self._bpy_text, self._attrib + self._bpy_attr

    def selectable(self):
        return self._bpy_selectable

    def get_cursor_coords(self, *args, **kwargs):
        # urwid gets confused if a nonselectable widget has a cursor position.
        if not self._bpy_selectable:
            return None
        return urwid.Edit.get_cursor_coords(self, *args, **kwargs)

    def render(self, size, focus=False):
        # XXX I do not want to have to do this, but listbox gets confused
        # if I do not (getting None out of get_cursor_coords because
        # we just became unselectable, then having this render a cursor)
        if not self._bpy_selectable:
            focus = False
        return urwid.Edit.render(self, size, focus=focus)

    def get_pref_col(self, size):
        # Need to make this deal with us being nonselectable
        if not self._bpy_selectable:
            return 'left'
        return urwid.Edit.get_pref_col(self, size)

    def move_cursor_to_coords(self, *args):
        if self._bpy_may_move_cursor:
            return urwid.Edit.move_cursor_to_coords(self, *args)
        return False

    def keypress(self, size, key):
        if urwid.command_map[key] in ['cursor up', 'cursor down']:
            # Do not handle up/down arrow, leave them for the repl.
            #sys.stderr.write("cursor keys")
            return key

        self._bpy_may_move_cursor = True
        try:
            if urwid.command_map[key] == 'cursor max left':
                self.edit_pos = 0
            elif urwid.command_map[key] == 'cursor max right':
                self.edit_pos = len(self.get_edit_text())
            elif urwid.command_map[key] == 'clear word':
                # ^w
                if self.edit_pos == 0:
                    return
                line = self.get_edit_text()
                # delete any space left of the cursor
                p = len(line[:self.edit_pos].strip())
                line = line[:p] + line[self.edit_pos:]
                # delete a full word
                # XXX: fugly word splitting heuristics, but better than just
                #      slitting on space
                np = max(
                        line.rfind(' ', 0, p),
                        line.rfind('.', 0, p-1),
                        line.rfind('(', 0, p-1),
                        line.rfind('=', 0, p-1)
                        ) + 1
                if np == -1:
                    line = line[p:]
                    np = 0
                else:
                    line = line[:np] + line[p:]
                self.set_edit_text(line)
                self.edit_pos = np
            elif urwid.command_map[key] == 'clear line':
                line = self.get_edit_text()
                self.set_edit_text(line[self.edit_pos:])
                self.edit_pos = 0
            elif key == 'backspace':
                line = self.get_edit_text()
                cpos = len(line) - self.edit_pos
                if not (cpos or len(line) % self.tab_length or line.strip()):
                    self.set_edit_text(line[:-self.tab_length])
                else:
                    return urwid.Edit.keypress(self, size, key)
            else:
                # TODO: Add in specific keypress fetching code here
                return urwid.Edit.keypress(self, size, key)
            return None
        finally:
            self._bpy_may_move_cursor = False

    def mouse_event(self, *args):
        self._bpy_may_move_cursor = True
        try:
            return urwid.Edit.mouse_event(self, *args)
        finally:
            self._bpy_may_move_cursor = False

class BPythonListBox(urwid.ListBox):
    """Like `urwid.ListBox`, except that it does not eat up and
    down keys.
    """
    def keypress(self, size, key):
        if key not in ["up", "down"]:
            return urwid.ListBox.keypress(self, size, key)
        return key

class Tooltip(urwid.BoxWidget):

    """Container inspired by Overlay to position our tooltip.

    bottom_w should be a BoxWidget.
    The top window currently has to be a listbox to support shrinkwrapping.

    This passes keyboard events to the bottom instead of the top window.

    It also positions the top window relative to the cursor position
    from the bottom window and hides it if there is no cursor.
    """

    def __init__(self, bottom_w, listbox):
        self.__super.__init__()

        self.bottom_w = bottom_w
        self.listbox = listbox
        # TODO: this linebox should use the 'main' color.
        self.top_w = urwid.LineBox(listbox)
        self.tooltip_focus = False

    def selectable(self):
        return self.bottom_w.selectable()

    def keypress(self, size, key):
        return self.bottom_w.keypress(size, key)

    def mouse_event(self, size, event, button, col, row, focus):
        # TODO: pass to top widget if visible and inside it.
        if not hasattr(self.bottom_w, 'mouse_event'):
            return False

        return self.bottom_w.mouse_event(
            size, event, button, col, row, focus)

    def get_cursor_coords(self, size):
        return self.bottom_w.get_cursor_coords(size)

    def render(self, size, focus=False):
        maxcol, maxrow = size
        bottom_c = self.bottom_w.render(size, focus)
        cursor = bottom_c.cursor
        if not cursor:
            # Hide the tooltip if there is no cursor.
            return bottom_c

        cursor_x, cursor_y = cursor
        if cursor_y * 2 < maxrow:
            # Cursor is in the top half. Tooltip goes below it:
            y = cursor_y + 1
            rows = maxrow - y
        else:
            # Cursor is in the bottom half. Tooltip fills the area above:
            y = 0
            rows = cursor_y

        # HACK: shrink-wrap the tooltip. This is ugly in multiple ways:
        # - It only works on a listbox.
        # - It assumes the wrapping LineBox eats one char on each edge.
        # - It is a loop.
        #   (ideally it would check how much free space there is,
        #   instead of repeatedly trying smaller sizes)
        while 'bottom' in self.listbox.ends_visible((maxcol - 2, rows - 3)):
            rows -= 1

        # If we're displaying above the cursor move the top edge down:
        if not y:
            y = cursor_y - rows

        # Render *both* windows focused. This is probably not normal in urwid,
        # but it works nicely.
        top_c = self.top_w.render((maxcol, rows),
                                  focus and self.tooltip_focus)

        combi_c = urwid.CanvasOverlay(top_c, bottom_c, 0, y)
        # Use the cursor coordinates from the bottom canvas.
        canvas = urwid.CompositeCanvas(combi_c)
        canvas.cursor = cursor
        return canvas

class URWIDInteraction(repl.Interaction):
    def __init__(self, config, statusbar, frame):
        repl.Interaction.__init__(self, config, statusbar)
        self.frame = frame
        urwid.connect_signal(statusbar, 'prompt_result', self._prompt_result)
        self.callback = None

    def confirm(self, q, callback):
        """Ask for yes or no and call callback to return the result"""

        def callback_wrapper(result):
            callback(result.lower() in (_('y'), _('yes')))

        self.prompt(q, callback_wrapper, single=True)

    def notify(self, s, n=10):
        return self.statusbar.message(s, n)

    def prompt(self, s, callback=None, single=False):
        """Prompt the user for input. The result will be returned via calling
        callback. Note that there can only be one prompt active. But the
        callback can already start a new prompt."""

        if self.callback is not None:
            raise Exception('Prompt already in progress')

        self.callback = callback
        self.statusbar.prompt(s, single=single)
        self.frame.set_focus('footer')

    def _prompt_result(self, text):
        self.frame.set_focus('body')
        if self.callback is not None:
            # The callback might want to start another prompt, so reset it
            # before calling the callback.
            callback = self.callback
            self.callback = None
            callback(text)


class NotIPythonKernel(Exception):
    pass

class IPythonHistory(repl.History):
    """A history mechanism that interacts with IPython.

    This relies on the standard IPython kernel, because it uses
    `get_ipyton().history_manager` to fetch results.

    As a fall back, local readline completion should be implemented when a new
    instance of IPythonHistory can not initialize and raises an error.
    """

    def __init__(self, repl):
        """The required argument is a handle on the repl, which will be ued to
        communicate with the IPython kernel. If a connection cannot be made,
        or no expected results are returned, we raise a NotIPythonKernel
        error, so that the vanilla readline completion can continue to be used
        as a fallback.
        """
        msg_id = repl.send_ipython('', silent=False, user_expressions={ 'hist':
            "list(get_ipython().history_manager.get_range())"})
        # XXX: for now we only grab history from current sesssion
            #"list(get_ipython().history_manager.get_tail(100))"})
                #silent=True)


        output = repl.ipython_get_child_msg(msg_id)['content']
        hist = eval(output['user_expressions']['hist']['data']['text/plain'])
        self.hist = hist
        repl.debug_docstring = str(hist)
        repl.debug_docstring = ''
        self.entries = ['']
        self.index = 0
        self.saved_line = ''
        self.duplicates = True # allow duplicates
        self.repl = repl
        self.load()
        #raise NotIPythonKernel()

    def load(self, *args, **kwargs):
        """Load history from a live IPython session.
        
        Arguments are ignored, and are only listed here for API compatibility
        with bpython's History class, which takes `filename` and `encoding`
        arguments, but those don't make sense in this instance.
        """
        # XXX: stopgap: get the history from ipython, write it to a file, and
        # proceed with the normal load after that
        for line in self.hist:
            self.append(line[-1])
            self.repl.stdout_hist += "\n" + line[-1]

    def save(self, *args, **kw):
        pass
        
class URWIDRepl(repl.Repl):

    _time_between_redraws = .05 # seconds
    rl_history_reset = False

    def __init__(self, event_loop, palette, interpreter, config):
        repl.Repl.__init__(self, interpreter, config)

        self._redraw_handle = None
        self._redraw_pending = False
        self._redraw_time = 0

        self.listbox = BPythonListBox(urwid.SimpleListWalker([]))

        self.tooltip = urwid.ListBox(urwid.SimpleListWalker([]))
        self.tooltip.grid = None
        self.overlay = Tooltip(self.listbox, self.tooltip)
        self.stdout_hist = ''

        self.frame = urwid.Frame(self.overlay)

        if urwid.get_encoding_mode() == 'narrow':
            input_filter = decoding_input_filter
        else:
            input_filter = None

        # This constructs a raw_display.Screen, which nabs sys.stdin/out.
        self.main_loop = urwid.MainLoop(
            self.frame, palette,
            event_loop=event_loop, unhandled_input=self.handle_input,
            input_filter=input_filter, handle_mouse=False)

        # String is straight from bpython.cli
        self.statusbar = Statusbar(config,
            _(" <%s> Rewind  <%s> Save  <%s> Pastebin "
              " <%s> Pager  <%s> Show Source ") %
              (config.undo_key, config.save_key, config.pastebin_key,
               config.last_output_key, config.show_source_key), self.main_loop)
        self.frame.set_footer(self.statusbar.widget)
        self.interact = URWIDInteraction(self.config, self.statusbar, self.frame)

        self.edits = []
        self.edit = None
        self.current_output = None
        self._completion_update_suppressed = False

        # Bulletproof: this is a value extract_exit_value accepts.
        self.exit_value = ()

        load_urwid_command_map(config)
        self.debug_docstring = ''
        self.ipython = self.connect_ipython_kernel()
        
        self.ipy_execution_count = '0'
        self.docstring_widget = None
    
    @property
    def ipy_ps1(self):
        return "In [%d]: " % (int(self.ipy_execution_count) + 1)

    def connect_ipython_kernel(self, s=''):
        """create kernel manager from IPKernelApp string
        such as '--shell=47378 --iopub=39859 --stdin=36778 --hb=52668' for IPython 0.11
        or just 'kernel-12345.json' for IPython 0.12

        XXX: copy-paste engineering from vim-ipython. Proceed with caution
        """
        def echo(x):
            print(x)

        try:
            import IPython
        except ImportError:
            raise ImportError("Could not find IPython. bipython needs it")
        from IPython.config.loader import KeyValueConfigLoader
        try:
            from IPython.kernel import (
                KernelManager,
                find_connection_file,
            )
        except ImportError:
            #  IPython < 1.0
            from IPython.zmq.blockingkernelmanager import BlockingKernelManager as KernelManager
            from IPython.zmq.kernelapp import kernel_aliases
            try:
                from IPython.lib.kernel import find_connection_file
            except ImportError:
                # < 0.12, no find_connection_file
                pass
            
        s = s.replace('--existing', '')
        if 'connection_file' in KernelManager.class_trait_names():
            # 0.12 uses files instead of a collection of ports
            # include default IPython search path
            # filefind also allows for absolute paths, in which case the search
            # is ignored
            try:
                # XXX: the following approach will be brittle, depending on what
                # connection strings will end up looking like in the future, and
                # whether or not they are allowed to have spaces. I'll have to sync
                # up with the IPython team to address these issues -pi
                if '--profile' in s:
                    k,p = s.split('--profile')
                    k = k.lstrip().rstrip() # kernel part of the string
                    p = p.lstrip().rstrip() # profile part of the string
                    fullpath = find_connection_file(k,p)
                else:
                    fullpath = find_connection_file(s.lstrip().rstrip())
            except IOError as e:
                self.echod(":IPython " + s + " failed")
                self.echod("^-- failed '" + s + "' not found")
                over_the_line()
            km = KernelManager(connection_file = fullpath)
            km.load_connection_file()
        else:
            if s == '':
                self.echod(":IPython 0.11 requires the full connection string")
                over_the_line()
            loader = KeyValueConfigLoader(s.split(), aliases=kernel_aliases)
            cfg = loader.load_config()['KernelApp']
            try:
                ip = '127.0.0.1'
                km = KernelManager(
                    shell_address=(ip, cfg['shell_port']),
                    sub_address=(ip, cfg['iopub_port']),
                    stdin_address=(ip, cfg['stdin_port']),
                    hb_address=(ip, cfg['hb_port']))
            except KeyError as e:
                self.echod(":IPython " +s + " failed")
                self.echod("^-- failed --"+e.message.replace('_port','')+" not specified")
                over_the_line()
                

        try:
            kc = km.client()
        except AttributeError:
            # 0.13
            kc = km
        kc.start_channels()

        self.send_ipython = kc.shell_channel.execute
        #XXX: backwards compatibility for IPython < 0.13
        sc = kc.shell_channel
        num_oinfo_args = len(inspect.getargspec(sc.object_info).args)
        if num_oinfo_args == 2:
            # patch the object_info method which used to only take one argument
            klass = sc.__class__
            klass._oinfo_orig = klass.object_info
            klass.object_info = lambda s,x,y: s._oinfo_orig(x)
        
        #XXX: backwards compatibility for IPython < 1.0
        if not hasattr(kc, 'iopub_channel'):
            kc.iopub_channel = kc.sub_channel
        self.km = km
        self.kc = kc
        print(km)
        msg_id = self.send_ipython('# bpython ' + version + ' connected\n')
        try:
            child = self.ipython_get_child_msg(msg_id)
        except Empty:
            over_the_line()

        self.send_ipython(bipy_func, silent=True)
        # TODO: get a proper history navigator
        #
        try:
            self.rl_history = IPythonHistory(self)
        except NotIPythonKernel:
            # We must not be running an IPython Kernel
            #sys.stderr.write(
            self.debug_docstring = "could not access IPython history, falling back to readline"
            sys.stderr.flush()
            pass
        self.ipython_set_pid()

        return km
    
    def _get_args(self):
        """Check if an unclosed parenthesis exists, then attempt to get the
        argspec() for it. On success, update self.argspec and return True,
        otherwise set self.argspec to None and return False"""

        self.current_func = None


        if not self.config.arg_spec:
            self.echo('i suck')
            return False

        #self.echod('\ri rule')
        # Get the name of the current function and where we are in
        # the arguments
        stack = [['', 0, '']]
        try:
            for (token, value) in PythonLexer().get_tokens(
                self.current_line()):
                if token is Token.Punctuation:
                    if value in '([{':
                        stack.append(['', 0, value])
                    elif value in ')]}':
                        stack.pop()
                    elif value == ',':
                        try:
                            stack[-1][1] += 1
                        except TypeError:
                            stack[-1][1] = ''
                        stack[-1][0] = ''
                    elif value == ':' and stack[-1][2] == 'lambda':
                        stack.pop()
                    else:
                        stack[-1][0] = ''
                elif (token is Token.Name or token in Token.Name.subtypes or
                      token is Token.Operator and value == '.'):
                    stack[-1][0] += value
                elif token is Token.Operator and value == '=':
                    stack[-1][1] = stack[-1][0]
                    stack[-1][0] = ''
                elif token is Token.Keyword and value == 'lambda':
                    stack.append(['', 0, value])
                else:
                    stack[-1][0] = ''
            while stack[-1][2] in '[{':
                stack.pop()
            _, arg_number, _ = stack.pop()
            func, _, _ = stack.pop()
        except IndexError:
            return False
        if not func:
            return False
      
        #self.echod('here we go, func is ' + func)
        self.current_func = func

        # XXX: this code needs to run on the ipython side
        #       - can we recreate an argspec on this side after getting it
        #       from the other side. ... break on through to the other side!
        #
        #       looks like we can. Just need to get an ArgSpec back

        self.argspec = self.ipython_get_argspec(func)

        if self.argspec:
            self.argspec.append(arg_number)
            return True
        return False

    
    def complete(self, tab=False):
        "bipython completion - punt to ipython"
        self.docstring = ''
        
        returned = self.ipython_process_msgs()

       
        #if returned:
        #    self.docstring = "\n".join(returned)

        if self.debug_docstring:
            self.docstring = self.debug_docstring

        if not self._get_args():
            self.argspec = None
        
        if self.current_func is not None:
            self.ipython_get_doc(self.current_func)

        pos = self.edit.edit_pos
        text = self.edit.get_edit_text()

        cw = self.cw() or ''

        if not cw and not tab:
            # don't trigger automatic completion on empty lines
            self.matches = []
            self.matches_iter.update()
            return False or self.docstring #and self.docstring.find('ipython') != -1
        #else:
        #    self.docstring = 'yak yak yak!'
        self.matches = self.ipython_complete(cw, text, pos)
        self.matches_iter.update(cw, self.matches)
        return bool(self.matches) or self.docstring

        #if tab:
        #    return bool(self.matches)
        #return False
        #cs = self.current_string()

    # Subclasses of Repl need to implement echo, current_line, cw
    def echod(self, orig_s):
        #self.write(orig_s)
        if self.edit:
            self.edit.set_caption(orig_s)

    def echo(self, orig_s):
        got_string = not isinstance(orig_s, list)
        s = orig_s
        if got_string:
            s = orig_s.rstrip('\n')
        if True:
            if self.current_output is None:
                # XXX: hacky post-parsing of output here..
                if not got_string:
                    self.current_output = orig_s
                else: 
                    self.current_output = urwid.Text(('output', s))
                if self.edit is None:
                    self.listbox.body.append(self.current_output)
                    # Focus the widget we just added to force the
                    # listbox to scroll. This causes output to scroll
                    # if the user runs a blocking call that prints
                    # more than a screenful, instead of staying
                    # scrolled to the previous input line and then
                    # jumping to the bottom when done.
                    self.listbox.set_focus(len(self.listbox.body) - 1)
                else:
                    self.listbox.body.insert(-1, self.current_output)
                    # The edit widget should be focused and *stay* focused.
                    # XXX TODO: make sure the cursor stays in the same spot.
                    self.listbox.set_focus(len(self.listbox.body) - 1)
            else:
                # XXX this assumes this all has "output" markup applied.
                if got_string:
                    self.current_output.set_text(
                            ('output', self.current_output.text + s))
                else:
                    self.current_output.set_text(
                            [('output', self.current_output.text)] + s)

        if got_string and orig_s.endswith('\n'):
            self.current_output = None

        # If we hit this repeatedly in a loop the redraw is rather
        # slow (testcase: pprint(__builtins__). So if we have recently
        # drawn the screen already schedule a call in the future.
        #
        # Unfortunately we may hit this function repeatedly through a
        # blocking call triggered by the user, in which case our
        # timeout will not run timely as we do not return to urwid's
        # eventloop. So we manually check if our timeout has long
        # since expired, and redraw synchronously if it has.
        if self._redraw_handle is None:
            self.main_loop.draw_screen()

            def maybe_redraw(loop, self):
                if self._redraw_pending:
                    loop.draw_screen()
                    self._redraw_pending = False

                self._redraw_handle = None

            self._redraw_handle = self.main_loop.set_alarm_in(
                self._time_between_redraws, maybe_redraw, self)
            self._redraw_time = time.time()
        else:
            self._redraw_pending = True
            now = time.time()
            if now - self._redraw_time > 2 * self._time_between_redraws:
                # The timeout is well past expired, assume we're
                # blocked and redraw synchronously.
                self.main_loop.draw_screen()
                self._redraw_time = now

    def current_line(self):
        """Return the current line (the one the cursor is in)."""
        if self.edit is None:
            return ''
        return self.edit.get_edit_text()

    def cw(self):
        """Return the current word (incomplete word left of cursor)."""
        if self.edit is None:
            return

        pos = self.edit.edit_pos
        text = self.edit.get_edit_text()
        if pos != len(text):
            # Disable autocomplete if not at end of line, like cli does.
            # XXX: I think we can make this compeltion work here -pi
            return

        # Stolen from cli. TODO: clean up and split out.
        if (not text or
            (not text[-1].isalnum() and text[-1] not in ('.', '_'))):
            return

        # Seek backwards in text for the first non-identifier char:
        for i, c in enumerate(reversed(text)):
            if not c.isalnum() and c not in ('.', '_'):
                break
        else:
            # No non-identifiers, return everything.
            return text
        # Return everything to the right of the non-identifier.
        return text[-i:]

    @property
    def cpos(self):
        if self.edit is not None:
            return len(self.current_line()) - self.edit.edit_pos
        return 0

    def _populate_completion(self):
        widget_list = self.tooltip.body
        while widget_list:
            widget_list.pop()
        # This is just me flailing around wildly. TODO: actually write.
        if self.complete():
            if self.argspec:
                # This is mostly just stolen from the cli module.
                func_name, args, is_bound, in_arg = self.argspec
                args, varargs, varkw, defaults = args[:4]
                kwonly, kwonly_defaults = [], {}
                markup = [('bold name', func_name),
                          ('name', ': (')]

                # the isinstance checks if we're in a positional arg
                # (instead of a keyword arg), I think
                if is_bound and isinstance(in_arg, int):
                    in_arg += 1

                # bpython.cli checks if this goes off the edge and
                # does clever wrapping. I do not (yet).
                for k, i in enumerate(args):
                    if defaults and k + 1 > len(args) - len(defaults):
                        kw = repr(defaults[k - (len(args) - len(defaults))])
                    else:
                        kw = None

                    if not k and str(i) == 'self':
                        color = 'name'
                    else:
                        color = 'token'

                    if k == in_arg or i == in_arg:
                        color = 'bold ' + color

                    if not py3:
                        # See issue #138: We need to format tuple unpacking correctly
                        # We use the undocumented function inspection.strseq() for
                        # that. Fortunately, that madness is gone in Python 3.
                        markup.append((color, inspect.strseq(i, str)))
                    else:
                        markup.append((color, str(i)))
                    if kw is not None:
                        markup.extend([('punctuation', '='),
                                       ('token', kw)])
                    if k != len(args) - 1:
                        markup.append(('punctuation', ', '))

                if varargs:
                    if args:
                        markup.append(('punctuation', ', '))
                    markup.append(('token', '*' + varargs))

                if kwonly:
                    if not varargs:
                        if args:
                            markup.append(('punctuation', ', '))
                        markup.append(('punctuation', '*'))
                    for arg in kwonly:
                        if arg == in_arg:
                            color = 'bold token'
                        else:
                            color = 'token'
                        markup.extend([('punctuation', ', '),
                                       (color, arg)])
                        if arg in kwonly_defaults:
                            markup.extend([('punctuation', '='),
                                           ('token', kwonly_defaults[arg])])

                if varkw:
                    if args or varargs or kwonly:
                        markup.append(('punctuation', ', '))
                    markup.append(('token', '**' + varkw))
                markup.append(('punctuation', ')'))
                widget_list.append(urwid.Text(markup))
            if self.matches:
                attr_map = {}
                focus_map = {'main': 'operator'}
                texts = [urwid.AttrMap(urwid.Text(('main', match)),
                                       attr_map, focus_map)
                         for match in self.matches]
                width = max(text.original_widget.pack()[0] for text in texts)
                gridflow = urwid.GridFlow(texts, width, 1, 0, 'left')
                widget_list.append(gridflow)
                self.tooltip.grid = gridflow
                self.overlay.tooltip_focus = False
            else:
                self.tooltip.grid = None
            self.frame.body = self.overlay
        else:
            self.frame.body = self.listbox
            self.tooltip.grid = None
        self.docstring_widget = urwid.Text(('comment', ''))
        widget_list.append(self.docstring_widget)
        self._populate_docstring()

    def _populate_docstring(self):
        "Make visible the docstring"
        self.docstring_widget.set_text(('comment', self.docstring))
    
    def clear_docstring(self):
        "remove the docstring"
        self.docstring_widget.set_text('')

    def reprint_line(self, lineno, tokens):
        edit = self.edits[-len(self.buffer) + lineno - 1]
        edit.set_edit_markup(list(format_tokens(tokens)))

    def getstdout(self):
        """This method returns the 'spoofed' stdout buffer, for writing to a
        file or sending to a pastebin or whatever."""

        return self.stdout_hist + '\n'

    def ask_confirmation(self, q):
        """Ask for yes or no and return boolean"""
        try:
            reply = self.statusbar.prompt(q)
        except ValueError:
            return False

        return reply.lower() in ('y', 'yes')

    def reevaluate(self):
        """Clear the buffer, redraw the screen and re-evaluate the history"""

        self.evaluating = True
        self.stdout_hist = ''
        self.f_string = ''
        self.buffer = []
        self.scr.erase()
        self.s_hist = []
        # Set cursor position to -1 to prevent paren matching
        self.cpos = -1

        self.prompt(False)

        self.iy, self.ix = self.scr.getyx()
        for line in self.history:
            if py3:
                self.stdout_hist += line + '\n'
            else:
                self.stdout_hist += line.encode(locale.getpreferredencoding()) + '\n'
            self.print_line(line)
            self.s_hist[-1] += self.f_string
            # I decided it was easier to just do this manually
            # than to make the print_line and history stuff more flexible.
            self.scr.addstr('\n')
            more = self.push(line)
            self.prompt(more)
            self.iy, self.ix = self.scr.getyx()

        self.cpos = 0
        indent = repl.next_indentation(self.s, self.config.tab_length)
        self.s = ''
        self.scr.refresh()

        if self.buffer:
            for _ in range(indent):
                self.tab()

        self.evaluating = False
        #map(self.push, self.history)
        #^-- That's how simple this method was at first :(

    def write(self, s):
        """For overriding stdout defaults"""
        if '\x04' in s:
            for block in s.split('\x04'):
                self.write(block)
            return
        if s.rstrip() and '\x03' in s:
            t = s.split('\x03')[1]
        else:
            t = s

        if not py3 and isinstance(t, unicode):
            t = t.encode(locale.getpreferredencoding())

        if not self.stdout_hist:
            self.stdout_hist = t
        else:
            self.stdout_hist += t

        self.echo(s)
        self.s_hist.append(s.rstrip())

    def ipython_set_pid(self):
        """
        Explicitly ask the ipython kernel for its pid
        """
        lines = '\n'.join(['import os', '_pid = os.getpid()'])
        msg_id = self.send_ipython(lines, silent=True, user_variables=['_pid'])

        # wait to get message back from kernel
        try:
            child = self.ipython_get_child_msg(msg_id)
        except Empty:
            #self.echo("no reply from IPython kernel")
            self.ipy_pid = None
            return
        try:
            pid = int(child['content']['user_variables']['_pid'])
        except TypeError: # change in IPython 1.0.dev moved this out
            pid = int(child['content']['user_variables']['_pid']['data']['text/plain'])
        except KeyError: # change in IPython 1.0.dev moved this out
            #self.echo("Could not get PID information, kernel not running Python?")
            pass
        self.ipy_pid = pid

    def ipython_interrupt_kernel_hack(self, signal_to_send=None):
        """
        Sends the interrupt signal to the remote kernel.  This side steps the
        (non-functional) ipython interrupt mechanisms.
        Only works on posix.
        """
        pid = self.ipy_pid
        if pid is None:
            # Avoid errors if we couldn't get pid originally,
            # by trying to obtain it now
            self.ipython_set_pid()
            pid = self.ipy_pid

            if pid is None:
                self.echo("cannot get kernel PID, Ctrl-C will not be supported")
                return
        if not signal_to_send:
            signal_to_send = signal.SIGINT

        self.echo("\n(KeyboardInterrupt)") # (sent to ipython: pid " +
            #"%i with signal %s)" % (pid, signal_to_send))
        try:
            os.kill(pid, int(signal_to_send))
        except OSError:
            self.echo("unable to kill pid %d" % pid)
            pid = None
        self.ipython_process_msgs()

    def ipython_get_argspec(self, func):
        self.send_ipython('', silent=True,
                user_expressions={'argspec': 'bipy_argspec("'+func+'")'})
        #for msg in self.kc.shell_channel.get_msgs():
        #    #msg = self.kc.get_shell_msg()['content']
        #    if 'argspec' not in msg['user_exprsessions']:
        #        self.echod("skipping" + str(msg))
        #    else:
        #        break
        msg = self.kc.get_shell_msg()['content']
        aspec = msg['user_expressions']['argspec']
        #self.echod(aspec['data'])
        if 'ename' in aspec:
            self.echod("got an error")
            return None

        return eval(aspec['data']['text/plain']) # relies on ArgSpec


    def ipython_complete(self, base, current_line, pos=None):
        #self.echo('\ncomplete called' + base + ' ' + current_line)
        msg_id = self.kc.shell_channel.complete(base, current_line, pos)
        try:
            #self.echod('\ntrying to get match for ' + base + " XXX")
            m = self.ipython_get_child_msg(msg_id)
            matches = m['content']['matches']
            #matches.insert(0,base) # the "no completion" version #not for bp
            # we need to be careful with unicode, because we can have unicode
            # completions for filenames (for the %run magic, for example). So the next
            # line will fail on those:
            #completions= [str(u) for u in matches]
            # because str() won't work for non-ascii characters
            # and we also have problems with unicode in vim, hence the following:
            #self.echo("\nmatches: " + " ".join(matches))
            return matches
        except Empty:
            self.echo("no reply from IPython kernel")
            return ['']

    def ipython_get_child_msg(self, msg_id):
        # XXX: message handling should be split into its own process in the future
        while True:
            # get_msg will raise with Empty exception if no messages arrive in 1 second
            m = self.kc.shell_channel.get_msg(timeout=1)
            if m['parent_header']['msg_id'] == msg_id:
                #self.echod('\n\tshell_channel: ' + str(m['content']))
                break
            else:
                #got a message, but not the one we were looking for
                #self.echod('\n\tshell_channel (skipping): ' + str(m['content']))
                pass
        return m
   
    def ipython_get_doc(self, func):
        #self.debug_docstring = 'doc called for ' + func
        #self.stdout_hist += "\nDEBUG: doc called for " + func
        #self.send_ipython('# ' + self.debug_docstring)
        try:
            level = 0
            msg_id = self.kc.shell_channel.object_info(func, level)
            doc = self.ipython_get_doc_msg(msg_id)
            if len(doc) == 0:
                doc = ['']
            self.docstring = "\n".join(doc)
        except IndexError:
            self.docstring = ''
        self._populate_docstring()

    def ipython_get_doc_msg(self, msg_id):
        n = 13 # longest field name (empirically)
        b=[]
        try:
            content = self.ipython_get_child_msg(msg_id)['content']
        except Empty:
            # timeout occurred
            return ["no reply from IPython kernel"]

        if not content['found']:
            return b

        # XXX: in vim-ipython I do all of these:
        #
        #    for field in ['type_name','base_class','string_form','namespace',
        #        'file','length','definition','source','docstring']:
        #
        #   But with argspec inspection, that seems too verbose.
        #
        ds = content.get('docstring','')
        if ds == '<no docstring>':
            b = ['']
        else:
            b = [ ds, '' ] 
        for field in ['base_class','string_form','namespace',
            'file','length','definition','source']:
            c = content.get(field,None)
            if c:
                if field in ['definition']:
                    c = strip_color_escapes(c).rstrip()
                s = field.replace('_',' ').title()+':'
                s = s.ljust(n)
                if c.find('\n')==-1:
                    b.append(s+c)
                else:
                    b.append(s)
                    b.extend(c.splitlines())
        return b
    
    def ipython_process_msgs(self):
        #b = ['\nIPY msgs']
        b = ['']
        status_prompt_out = '\nOut[%(line)d]: ' 
        status_prompt_in = '\n\nIn [%(line)d]: ' 
        msgs = self.kc.iopub_channel.get_msgs()
        for m in msgs:
            #db.append(str(m).splitlines())
            s = ''
            #self.echod('\n\tiopub channel: ' + str(m['content']))
            if 'msg_type' not in m['header']:
                # debug information
                #echo('skipping a message on sub_channel','WarningMsg')
                #echo(str(m))
                continue
            header = m['header']['msg_type']
            if header == 'status':
                continue
            elif header == 'stream':
                # TODO: alllow for distinguishing between stdout and stderr (using
                # custom syntax markers in the vim-ipython buffer perhaps), or by
                # also echoing the message to the status bar
                s = strip_color_escapes(m['content']['data'])
                #self.echod('ipython stream' + s)
            elif header == 'pyout':
                s = [('error', status_prompt_out % {'line':
                    m['content']['execution_count']})]
                s += [('output', m['content']['data']['text/plain'])]
            elif header == 'display_data':
                # TODO: handle other display data types (HMTL? images?)
                s += m['content']['data']['text/plain']
            elif header == 'pyin':
                # TODO: the next line allows us to resend a line to ipython if
                # %doctest_mode is on. In the future, IPython will send the
                # execution_count on subchannel, so this will need to be updated
                # once that happens
                # TODO: ignore if we're the ones who sent this, since that's
                # already been typed out by the user and is still on the
                # screen.
                line_number = m['content'].get('execution_count', 0)
                if line_number != self.ipy_execution_count:
                    #XXX: ignore these for now, assume we've typed them
                    prompt = status_prompt_in % {'line': line_number}
                    s = prompt
                    # add a continuation line (with trailing spaces if the prompt has them)
                    dots = '.' * len(prompt.rstrip())
                    dots += prompt[len(prompt.rstrip()):]
                    s += m['content']['code'].rstrip().replace('\n', '\n' + dots)
                # TODO - recolorize output here
                # call on_input_change for the right lines
                #tokens = self.tokenize(code, False)
                #edit.set_edit_markup(list(format_tokens(tokens)))
            if 'execution_count' in m['content']:
                self.ipy_execution_count = m['content']['execution_count']

            elif header == 'pyerr':
                c = m['content']
                # XXX: when we learn how to parse color escapes for urwid to
                # handle nicely, don't strip them on the next line
                s = "\n".join(map(strip_color_escapes,c['traceback']))
                s += c['ename'] + ":" + c['evalue']

            if isinstance(s, list):
                b.extend(s)
            elif s.find('\n') == -1:
                b.append(s)
            else:
                b.extend(s.splitlines())
            self.echo(s)
        return b

    def push(self, s, insert_into_history=True):
        # Restore the original SIGINT handler. This is needed to be able
        # to break out of infinite loops. If the interpreter itself
        # sees this it prints 'KeyboardInterrupt' and returns (good).
        orig_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.default_int_handler)
        # Pretty blindly adapted from bpython.cli
        try:
            msg_id = self.send_ipython(s)
            #self.rl_history.enter(s)
            if hasattr(repl.Repl, 'insert_into_history'):
                # this is only in unreleased version of bpython
                self.insert_into_history(s)
                # on the IPython side, at least for the Python kernel, history
                # is managed for us by the history manager, so there's no need
                # to do anything here.
            if self.edit is not None:
                self.edit.make_readonly()
            self.buffer = []
            self.edit = None
            ret_msg = self.ipython_get_child_msg(msg_id)
            if 'execution_count' in ret_msg['content']:
                self.ipy_execution_count = ret_msg['content']['execution_count']
            #self.echod('\n shell: ' + str(ret_msg['content']))
            #self.send_ipython("###retmsg " + str(ret_msg))
            #self.send_ipython("###retmsg " + str(returned))
            #self.prompt(
            #self.echod("\n#ipython".join(returned))
            #x = repl.Repl.push(self, s, insert_into_history) 
            #self.echod("\n#ipython".join(returned))
            #self.send_ipython("x = " + str(x))
            #+ "\n".join(returned) 
            return False
        except SystemExit as e:
            self.exit_value = e.args
            raise urwid.ExitMainLoop()
        except KeyboardInterrupt:
            # KeyboardInterrupt happened between the except block around
            # user code execution and this code. This should be rare,
            # but make sure to not kill bpython here, so leaning on
            # ctrl+c to kill buggy code running inside bpython is safe.
            self.keyboard_interrupt()
        except Empty:
            # let's wait until  Ctrl-C or we get some results
            self.prompt(False)
            while True:
                # we've submitted, so any pending output should go below
                try:
                    self.ipython_process_msgs()
                    ret_msg = self.ipython_get_child_msg(msg_id)
                    if 'execution_count' in ret_msg['content']:
                        self.ipy_execution_count = ret_msg['content']['execution_count']
                except Empty:
                    pass
                except KeyboardInterrupt:
                    self.keyboard_interrupt()
                    break
                else:
                    break
        finally:
            signal.signal(signal.SIGINT, orig_handler)

    def start(self):
        self.prompt(False)

    def keyboard_interrupt(self):
        # If the user is currently editing, interrupt him. This
        # mirrors what the regular python REPL does.
        self.ipython_interrupt_kernel_hack()
        if self.edit is not None:
            # XXX this is a lot of code, and I am not sure it is
            # actually enough code. Needs some testing.
            #self.edit.insert_text('^C')
            self.edit.set_edit_markup(('error','^C'))
            self.edit.make_readonly()
            self.edit = None
            self.buffer = []
            self.echo('\rKeyboardInterruptA')
            self.prompt(False)
        else:
            # I do not quite remember if this is reachable, but let's
            # be safe.
            self.echo('KeyboardInterruptB')

        time.sleep(.5) # give the kill signal a chance to get processed
        self.ipython_process_msgs()

    def prompt(self, more):
        # Clear current output here, or output resulting from the
        # current prompt run will end up appended to the edit widget
        # sitting above this prompt:
        self.current_output = None
        # XXX is this the right place?
        #self.rl_history.reset()
        # XXX what is s_hist?

        # We need the caption to use unicode as urwid normalizes later
        # input to be the same type, using ascii as encoding. If the
        # caption is bytes this breaks typing non-ascii into bpython.
        # Currently this decodes using ascii as I do not know where
        # ps1 is getting loaded from. If anyone wants to make
        # non-ascii prompts work feel free to fix this.
        if not more:
            caption = ('prompt', "\n" + self.ipy_ps1)
            self.stdout_hist += self.ps1
        else:
            caption = ('prompt_more', self.ps2.decode('ascii'))
            self.stdout_hist += self.ps2
        self.edit = BPythonEdit(self.config, caption=caption)

        urwid.connect_signal(self.edit, 'change', self.on_input_change)
        urwid.connect_signal(self.edit, 'edit-pos-changed',
                             self.on_edit_pos_changed)
        # Do this after connecting the change signal handler:
        self.edit.insert_text(4 * self.next_indentation() * ' ')
        self.edits.append(self.edit)
        self.listbox.body.append(self.edit)
        self.listbox.set_focus(len(self.listbox.body) - 1)
        # Hide the tooltip
        self.frame.body = self.listbox

    def on_input_change(self, edit, text):
        # TODO: we get very confused here if "text" contains newlines,
        # so we cannot put our edit widget in multiline mode yet.
        # That is probably fixable... !!!!! ARGH!!!
        # Yes, fix this -pi
        #if not edit.startswith(self.ipy_ps1):
        #edit.set_caption(self.ipy_ps1)
        tokens = self.tokenize(text, False)
        #self.debug_docstring = str(list(format_tokens(tokens)))
        ipy_tok = [('token', u''), ('number', self.ipy_ps1)]

        edit.set_edit_markup(ipy_tok + list(format_tokens(tokens)))
        if not self._completion_update_suppressed:
            # If we call this synchronously the get_edit_text() in repl.cw
            # still returns the old text...
            self.main_loop.set_alarm_in(
                0, lambda *args: self._populate_completion())

    def on_edit_pos_changed(self, edit, position):
        """Gets called when the cursor position inside the edit changed.
        Rehighlight the current line because there might be a paren under
        the cursor now."""
        tokens = self.tokenize(self.current_line(), False)
        edit.set_edit_markup(list(format_tokens(tokens)))

    def handle_input(self, event):
        # Since most of the input handling here should be handled in the edit
        # instead, we return here early if the edit doesn't have the focus.
        if self.frame.get_focus() != 'body':
            return

        if event == 'enter':
            inp = self.edit.get_edit_text()
            self.history.append(inp)
            self.edit.make_readonly()
            # XXX what is this s_hist thing?
            self.stdout_hist += inp + '\n'
            self.edit = None
            # This may take a while, so force a redraw first:
            self.main_loop.draw_screen()
            more = self.push(inp)
            self.prompt(more)
            # XXX: fetching all history is expensive, but better than nothing
            # for now
            self.rl_history_reset = True
        elif event == 'ctrl d':
            # ctrl+d on an empty line exits, otherwise deletes
            if self.edit is not None:
                if not self.edit.get_edit_text():
                    raise urwid.ExitMainLoop()
                else:
                    self.main_loop.process_input(['delete'])
        elif urwid.command_map[event] == 'cursor up':
            # "back" from bpython.cli
            if self.rl_history_reset:
                self.rl_history = IPythonHistory(self)
                self.rl_history_reset = False
            self.rl_history.enter(self.edit.get_edit_text())
            self.edit.set_edit_text('')
            self.edit.insert_text(self.rl_history.back()) # + "#previous")
        elif urwid.command_map[event] == 'cursor down':
            # "fwd" from bpython.cli
            self.rl_history.enter(self.edit.get_edit_text())
            self.edit.set_edit_text('')
            self.edit.insert_text(self.rl_history.forward()) # + "#next")
        elif urwid.command_map[event] == 'next selectable':
            self.tab()
        elif urwid.command_map[event] == 'prev selectable':
            self.tab(True)
        elif event == 'esc':
            self.ipython_get_doc('')
            #self.clear_docstring() # why is this so slow?, ARGH!
            # XXX: tab redraws really quickly
        else:
            self.echo(repr(event))

    def tab(self, back=False):
        """Process the tab key being hit.

        If the line is blank or has only whitespace: indent.

        If there is text before the cursor: cycle completions.

        If `back` is True cycle backwards through completions, and return
        instead of indenting.

        Returns True if the key was handled.
        """
        self._completion_update_suppressed = True
        try:
            # Heavily inspired by cli's tab.
            text = self.edit.get_edit_text()
            if not text.lstrip() and not back:
                x_pos = len(text) - self.cpos
                num_spaces = x_pos % self.config.tab_length
                if not num_spaces:
                    num_spaces = self.config.tab_length

                self.edit.insert_text(' ' * num_spaces)
                return True

            if not self.matches_iter:
                self.complete(tab=True)
                cw = self.current_string() or self.cw()
                if not cw:
                    return True
            else:
                cw = self.matches_iter.current_word


            if self.matches:
                self.edit.set_edit_text(text[:-len(cw)])
                if self.matches_iter:
                    self.edit.set_edit_text(
                            text[:-len(self.matches_iter.current())])

                if back:
                    current_match = self.matches_iter.previous()
                else:
                    current_match = next(self.matches_iter)
                if current_match:
                    self.overlay.tooltip_focus = True
                    if self.tooltip.grid:
                        self.tooltip.grid.set_focus(self.matches_iter.index)
                    self.edit.insert_text(current_match)
                self.ipython_get_doc(current_match)
            return True
        finally:
            self._completion_update_suppressed = False

def main(args=None, locals_=None, banner=None):
    translations.init()

    import argparse
    parser = argparse.ArgumentParser(
            description='the boldly indiscriminate Python interpreter')
    parser.add_argument( '-v','--version', action='version',
            version='%(prog)s ' + version)
    parser.parse_known_args()

    # ok, it's not nice, i'm hiding all of these params, but LTS.
    #
    # TODO: maybe support displays other than raw_display?
    config, options, exec_args = bpargs.parse(args, (
            'Urwid options', None, [
                Option('--twisted', '-T', action='store_true',
                       help=_('Run twisted reactor.')),
                Option('--reactor', '-r',
                       help=_('Select specific reactor (see --help-reactors). '
                       'Implies --twisted.')),
                Option('--help-reactors', action='store_true',
                       help=_('List available reactors for -r.')),
                Option('--plugin', '-p',
                       help=_('twistd plugin to run (use twistd for a list). '
                       'Use "--" to pass further options to the plugin.')),
                Option('--server', '-s', type='int',
                       help=_('Port to run an eval server on (forces Twisted).')),
                ]))

    if options.help_reactors:
        try:
            from twisted.application import reactors
            # Stolen from twisted.application.app (twistd).
            for r in reactors.getReactorTypes():
                print('    %-4s\t%s' % (r.shortName, r.description))
        except ImportError:
            sys.stderr.write('No reactors are available. Please install '
                'twisted for reactor support.\n')
        return

    # XXX: had to interject myself here to fix the blueness of comments
    config.color_scheme['comment'] = 'g'
    config.color_scheme['prompt'] = 'b'

    palette = [
        (name, COLORMAP[color.lower()], 'default',
         'bold' if color.isupper() else 'default')
        for name, color in config.color_scheme.items()]
    palette.extend([
            ('bold ' + name, color + ',bold', background, monochrome)
            for name, color, background, monochrome in palette])

    if options.server or options.plugin:
        options.twisted = True

    if options.reactor:
        try:
            from twisted.application import reactors
        except ImportError:
            sys.stderr.write('No reactors are available. Please install '
                'twisted for reactor support.\n')
            return
        try:
            # XXX why does this not just return the reactor it installed?
            reactor = reactors.installReactor(options.reactor)
            if reactor is None:
                from twisted.internet import reactor
        except reactors.NoSuchReactor:
            sys.stderr.write('Reactor %s does not exist\n' % (
                    options.reactor,))
            return
        event_loop = TwistedEventLoop(reactor)
    elif options.twisted:
        try:
            from twisted.internet import reactor
        except ImportError:
            sys.stderr.write('No reactors are available. Please install '
                'twisted for reactor support.\n')
            return
        event_loop = TwistedEventLoop(reactor)
    else:
        # None, not urwid.SelectEventLoop(), to work with
        # screens that do not support external event loops.
        event_loop = None
    # TODO: there is also a glib event loop. Do we want that one?

    # __main__ construction from bpython.cli
    if locals_ is None:
        main_mod = sys.modules['__main__'] = ModuleType('__main__')
        locals_ = main_mod.__dict__

    if options.plugin:
        try:
            from twisted import plugin
            from twisted.application import service
        except ImportError:
            sys.stderr.write('No twisted plugins are available. Please install '
                'twisted for twisted plugin support.\n')
            return

        for plug in plugin.getPlugins(service.IServiceMaker):
            if plug.tapname == options.plugin:
                break
        else:
            sys.stderr.write('Plugin %s does not exist\n' % (options.plugin,))
            return
        plugopts = plug.options()
        plugopts.parseOptions(exec_args)
        serv = plug.makeService(plugopts)
        locals_['service'] = serv
        reactor.callWhenRunning(serv.startService)
        exec_args = []
    interpreter = repl.Interpreter(locals_, locale.getpreferredencoding())

    # This nabs sys.stdin/out via urwid.MainLoop
    myrepl = URWIDRepl(event_loop, palette, interpreter, config)

    if options.server:
        factory = EvalFactory(myrepl)
        reactor.listenTCP(options.server, factory, interface='127.0.0.1')

    if options.reactor:
        # Twisted sets a sigInt handler that stops the reactor unless
        # it sees a different custom signal handler.
        def sigint(*args):
            reactor.callFromThread(myrepl.keyboard_interrupt)
        signal.signal(signal.SIGINT, sigint)

    # Save stdin, stdout and stderr for later restoration
    orig_stdin = sys.stdin
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    # urwid's screen start() and stop() calls currently hit sys.stdin
    # directly (via RealTerminal.tty_signal_keys), so start the screen
    # before swapping sys.std*, and swap them back before restoring
    # the screen. This also avoids crashes if our redirected sys.std*
    # are called before we get around to starting the mainloop
    # (urwid raises an exception if we try to draw to the screen
    # before starting it).
    def run_with_screen_before_mainloop():
        try:
            # Currently we just set this to None because I do not
            # expect code hitting stdin to work. For example: exit()
            # (not sys.exit, site.py's exit) tries to close sys.stdin,
            # which breaks urwid's shutdown. bpython.cli sets this to
            # a fake object that reads input through curses and
            # returns it. When using twisted I do not think we can do
            # that because sys.stdin.read and friends block, and we
            # cannot re-enter the reactor. If using urwid's own
            # mainloop we *might* be able to do something similar and
            # re-enter its mainloop.
            sys.stdin = None #FakeStdin(myrepl)
            sys.stdout = myrepl
            sys.stderr = myrepl

            myrepl.main_loop.set_alarm_in(0, start)

            while True:
                try:
                    myrepl.main_loop.run()
                except KeyboardInterrupt:
                    # HACK: if we run under a twisted mainloop this should
                    # never happen: we have a SIGINT handler set.
                    # If we use the urwid select-based loop we just restart
                    # that loop if interrupted, instead of trying to cook
                    # up an equivalent to reactor.callFromThread (which
                    # is what our Twisted sigint handler does)
                    myrepl.main_loop.set_alarm_in(
                        0, lambda *args: myrepl.keyboard_interrupt())
                    continue
                break

        finally:
            sys.stdin = orig_stdin
            sys.stderr = orig_stderr
            sys.stdout = orig_stdout

    # This needs more thought. What needs to happen inside the mainloop?
    def start(main_loop, user_data):
        if exec_args:
            bpargs.exec_code(interpreter, exec_args)
            if not options.interactive:
                raise urwid.ExitMainLoop()
        if not exec_args:
            sys.path.insert(0, '')
            # this is CLIRepl.startup inlined.
            filename = os.environ.get('PYTHONSTARTUP')
            if filename and os.path.isfile(filename):
                with open(filename, 'r') as f:
                    if py3:
                        interpreter.runsource(f.read(), filename, 'exec')
                    else:
                        interpreter.runsource(f.read(), filename, 'exec',
                                              encode=False)

        if banner is not None:
            repl.write(banner)
            repl.write('\n')
        myrepl.start()

        # This bypasses main_loop.set_alarm_in because we must *not*
        # hit the draw_screen call (it's unnecessary and slow).
        def run_find_coroutine():
            if find_coroutine():
                main_loop.event_loop.alarm(0, run_find_coroutine)

        run_find_coroutine()

    myrepl.main_loop.screen.run_wrapper(run_with_screen_before_mainloop)

    if config.flush_output and not options.quiet:
        sys.stdout.write(myrepl.getstdout())
    if hasattr(sys.stdout, "flush"):
        sys.stdout.flush()
    return repl.extract_exit_value(myrepl.exit_value)

def load_urwid_command_map(config):
    urwid.command_map[key_dispatch[config.up_one_line_key]] = 'cursor up'
    urwid.command_map[key_dispatch[config.down_one_line_key]] = 'cursor down'
    urwid.command_map[key_dispatch['C-a']] = 'cursor max left'
    urwid.command_map[key_dispatch['C-e']] = 'cursor max right'
    urwid.command_map[key_dispatch[config.pastebin_key]] = 'pastebin'
    urwid.command_map[key_dispatch['C-f']] = 'cursor right'
    urwid.command_map[key_dispatch['C-b']] = 'cursor left'
    urwid.command_map[key_dispatch['C-d']] = 'delete'
    urwid.command_map[key_dispatch[config.clear_word_key]] = 'clear word'
    urwid.command_map[key_dispatch[config.clear_line_key]] = 'clear line'

"""
            'clear_screen': 'C-l',
            'cut_to_buffer': 'C-k',
            'down_one_line': 'C-n',
            'exit': '',
            'last_output': 'F9',
            'pastebin': 'F8',
            'save': 'C-s',
            'show_source': 'F2',
            'suspend': 'C-z',
            'undo': 'C-r',
            'up_one_line': 'C-p',
            'yank_from_buffer': 'C-y'},
"""
def over_the_line():
    "This is a league game, Smokey"
    import sys
    sys.stderr.write("\n")
    sys.stderr.write("""Unable to connect to IPython:
    Either it's busy executing, or you haven't started one. 
    use `ipython console` in another shell first, or open a
    new IPython Notebook\n""")
    sys.exit(1)

if __name__ == '__main__':
    sys.exit(main())

