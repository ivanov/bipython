bipython
=========

![bipython logo](http://bipython.org/bipython_logo.png)


the boldly indiscriminate python interpreter
--------------------------------------------

*"...because you shouldn't have to choose."*

PROLOGUE
--------

   > Two interpreters, both alike in dignity,  
   > In fair Pythona, where we lay our scene,  
   > From ancient grudge break to new mutiny,  
   > Where civil code makes git commits unclean.  
   > From forth the fatal loins of these two foes  
   > A newer kind of strager's given life;  
   > Whose misadventured piteous overthrows  
   > Doth with its birth bury its parents' strife.  

ACT I
------

*Enter `bpython` and `ipython`*

[**`bpython`**](http://bpython-interpreter.org/)

   > I'm a fancy terminal-based interface to the Python interpreter.  I give you  
   > inline syntax highlighting and auto-completion prompts as you type, and I'll  
   > even automatically show you a little tooltip with a docstring and parameter  
   > list as soon as you hit `(` to make the function call, so you always know  
   > what you're doing! I'm svelte and proud of it - I don't try to do all of the  
   > shenanigans that `ipython` does with the shell and the web, but the cool kids  
   > love my rewind feature for demos. I strive to make interactive python coding  
   > a joy!

[**`ipython`**](http://ipython.org/)
    
   > I'm an awesome *suite* of interactive computing ideas that work together.  
   > For millenia, I've given you tab-completion and object introspection via  
   > `obj?` instead of `help(obj)` in Python. I also have sweet shell features,  
   > special magic commands (`%run`, `%timeit`, `%matplotlib`, etc.) and a   
   > history mechanism for both input (command history) and output (results   
   > caching).  

   > More recently, I've decoupled the REPL into clients and kernels, allowing  
   > them to run on independent of each other. One popular client is the   
   > IPython Notebook which allows you to write code and prose using a web   
   > browser, sending code to the kernel for execution and getting rich media   
   > results back inline. The decoupling of clients and kernels also allows   
   > multiple clients to interact with the same kernel, so you can hook-up to   
   > that same running kernel from the terminal. The terminal workflow makes   
   > more sense for some things, but my user interface there isn't as polished  
   > as `bpython`'s.  

*Enter `bipython`*

[**`bipython`**](http://bipython.org/)

   > By your powers combined... I am **`bipython`**!


*Exeunt*


Getting Started
----------------

    pip install -U bipython

You will need at least IPython with ZeroMQ support, urwid, and bpython...  
`pip install -U ipython[zmq] urwid bpython`

For now, you'll need to have a running ipython kernel before running bipython.
You can do this by either opening a notebook, or `ipython console`.


The power is yours!

TODO / ISSUES:
--------------

    [ ] MUSTFIX: multiline input not yet supported - limitation inherited from bpython's
        urwid code, which I found out too late.

        [ ] multiline input will be a bit tricky, will need to hold off and not
            submit to ipython until the multiline is completed. 

        [ ] would also be nice to get local completion in the case of long input cells

    [ ] MUSTFIX: up/down arrow keys for history don't work yet.

        [ ] maybe i should hook into interp and just turn that into a no-op,
            that way i can keep the current (cheap) history as is?


    [ ] see if I can put in workaround for stable bpython 
        - v0.12 works, so says Anthony
        - can I also make 0.11-1.1 work? (that's what Ubuntu 13.10 shipped)

    [ ] need to release today!

    [ ] implement Rewind feature

    [x] got monospaced theme picked out for pelican

    [ ] insert "fork me on github" overlay there.

    [x] colorize in and out prompts

    [ ] re-colorize the blue docstring stuff - make it magenta

    [x] only show docstring in tooltip

    [x] change prompt

    [ ] Maybe: set the username to bipython, and don't print those in the In prompt
        if we've sent them (this won't work in an ideal manner if we have more than
        one bipython client connected, but we can cross that bridge when we get
        to it (using a uuid suffix or something like that)

    [x] stream does not get printed currently.

    [ ] colorize tracebacks too
        - for this, we'll need an ansi escape parser - IPython has one that's
          implemented in javascript IIRC?

    [x] oops: while True: time.sleep(1); print "hi" breaks it
        - i think i need to listen to busy / idle events and react accordingly
          (giving back or not giving back the prompt in bipython)
        - or just hand the Queue.Empty case

    [x] handle keyboard interrupt
        - this is important! (of course it only works locally, but better than
          nothing)

    [ ] oh crap! I need twisted event loop for the urwid stuff to work?! goddamn
        it. Investigate how easy it is to port what I have back to the cli
        version of bpython code

    [ ] LOW: make ctrl-w delete word - with '.' being a word separator

    [ ] how do i keep the completion tooltip from going on top of wherever i'm
        typing - seems like it's hardcoded to do that after going half-way down
        the screen

        [ ] alt: use escape to remove it?

    [ ] colorize / pygemntize the pyin results - damn it - that requires hooking
        into the lexer again...

    [ ] setup sigalarm or setup eventloop to check for new messages' arrival
        - we already do it on typing, i think...

    [ ] print from elswhere - then <space> in bipython freezes it (if the
        completion thing was already open
        - this can be fixed by not printing docstring like i do for debugging
          - actually, no, that doesn't work

    [ ] ctrl-w shouldn't remove space before the cur word.

    [ ] look for ps1 ps2 for hints where continuation happens

    [ ] when receiving stream message, write to stdout history, the way urwid
        likes to do

    [ ] looks like i won't finish this today, no joke :\

    [x] update execution_count in place while typing

    [x] just need the highlighting to start AFTER In[ ]  
        (it doesn't account for caption)
        [ ] doesn't seem to want to color it green though

    [ ] start its own kernel if --existing flag not given

    [ ] gracefully handle input/output newlines when we didn't initiate it.

    [ ] obj? doesn't show up in bipython - intercept it to be a oinfo req like in
        vim-ipython - yes. do that.

    [x] make logo

    related projects:
        bpython-interpreter.org
        ipython.org
        vim-ipython

    [ ] flag
        thank you Michael Page - 1998
        Pantone Color #226--Magenta (Hex: #D70270) (RGB: 215, 2, 112)
        Pantone Color #258--Deep Lavender (Hex: #734F96) (RGB: 115, 79, 150)
        Pantone Color #286--Royal (Hex: #0038A8) (RGB: 0, 56, 168)

        The flag's aspect ratio is not fixed but 2:3 and 3:5 are often used, in
        common with many other flags

    [x] make bipython twitter account
    [ ] tweet at https://twitter.com/bpythonrepl and @IPythonDev

    [x] merge in anthony's old spooning forking commit.

    [ ] use python setup.py register to register it.

    [x] perform the git surgery to put all of my commits into bipython repo (so
        i can start getting anthony's feedback, if he wants to / can play)

    [ ] TODO: ansi color escape handling

    [x] MUSTFIX: tab-completion of magics.

        [x] fix introduced regression: tab completing on something that has no
            matched will delete the match

        [x] tab-completion should trigger docstring tooltip update

        [ ] another bug: `xdel<tab>^h<tab>`
            - first tab expand %, second one adds an extra % to the front

    [ ] figure out how much bpython i need.

    [ ] make animation of bpython and ipython logos going toward each other,
        then an explosion and the bipython logo emerging from the ashes.

    [x] make sure we get the pid to enable keyboard interrupt on start -
        otherwise, if we try to get it after we launch something we want to
        interrupt, we're screwed.

    [x] Ctrl-C should process messages as well - should block until interrupt
        completed

    [ ] set a time-out for completion and return empty if it's too slow (or the
        kernel is busy)

    [x] starting while True: print time.sleep(1) will print above the current
        line

    [x] looks like if there was output already on submission, stuff gets printed
        there.

    [x] process io_pub message on every completion to put them into the bpython
        user interface.


    [x] getting the argspec as bpython does it requires pulling in all of
        bpython/introspection.py - which is a bit much just to get the __init__
        handling. Let's just do the simple thing.

        let's remember to document that we're not going to use the AttrCleaner

        damn, doesn't look like that's gonna work. ok, let's port it all over to be
        standalone (so where ipython kernel is running doesn't need bpython)

        [ ] also - will need to think about how to gracefully handle non-python
            kernels with this.

        [ ] don't ship inspection_standalone every time you connect, check if
            another bipython connection has already executed it on the kernel.

    [ ] syntax highlighting for ipython magics - otherwise PythonLexer will choke

    [ ] ask bob to be added to related projects on bpython-interpreter.org

    [ ] make screencast demo
