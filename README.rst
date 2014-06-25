bipython
========

.. figure:: http://bipython.org/bipython_logo.png
   :alt: bipython logo

the boldly indiscriminate python interpreter
--------------------------------------------

*"...because you shouldn't have to choose."*

PROLOGUE
--------

    | Two interpreters, both alike in dignity,
    | In fair Pythona, where we lay our scene,
    | From ancient grudge break to new mutiny,
    | Where civil code makes git commits unclean.
    | From forth the fatal loins of these two foes
    | A newer kind of stranger's given life;
    | Whose misadventured piteous overthrows
    | Doth with its birth bury its parents' strife.

ACT I
-----

*Enter ``bpython`` and ``ipython``*

`**``bpython``** <http://bpython-interpreter.org/>`__

    | I'm a fancy terminal-based interface to the Python interpreter. I give you
    | inline syntax highlighting and auto-completion prompts as you type, and I'll
    | even automatically show you a little tooltip with a docstring and parameter
    | list as soon as you hit ``(`` to make the function call, so you always know
    | what you're doing! I'm svelte and proud of it - I don't try to do all of the
    | shenanigans that ``ipython`` does with the shell and the web, but the cool kids
    | love my rewind feature for demos. I strive to make interactive python coding
    | a joy!

`**``ipython``** <http://ipython.org/>`__

    | I'm an awesome *suite* of interactive computing ideas that work together.
    | For millennia, I've given you tab-completion and object introspection via
    | ``obj?`` instead of ``help(obj)`` in Python. I also have sweet shell features,
    | special magic commands (``%run``, ``%timeit``, ``%matplotlib``, etc.) and a
    | history mechanism for both input (command history) and output (results
    | caching).  
    |
    | More recently, I've decoupled the REPL into clients and kernels, allowing
    | them to run on independent of each other. One popular client is the
    | IPython Notebook which allows you to write code and prose using a web
    | browser, sending code to the kernel for execution and getting rich media
    | results back inline. The decoupling of clients and kernels also allows
    | multiple clients to interact with the same kernel, so you can hook-up to
    | that same running kernel from the terminal. The terminal workflow makes
    | more sense for some things, but my user interface there isn't as polished
    | as ``bpython``'s.

*Enter ``bipython``*

`**``bipython``** <http://bipython.org/>`__

    By your powers combined... I am **``bipython``**!

*Exeunt*

The Power is Yours!
-------------------

::

    pip install  bipython

``bipython`` requires ipython, pyzmq, bpython, and urwid.

For now, you'll need to have a running ipython kernel before running
``bipython``. You can do this by either opening a notebook or running
``ipython console``. It won't always be like this, I'll fix it as soon
as I can, but it'll be sooner `with your help over
ivanov/bipython <https://github.com/ivanov/bipython>`__.

After that, just run ``bipython`` and enjoy the ride.

Copyright (c) 2014, `Paul Ivanov <http://pirsquared.org/blog>`__
