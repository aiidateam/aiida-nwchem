============
Installation
============


1. Get the Plugin and Install
+++++++++++++++++++++++++++++

1a. Latest Release
------------------

The latest stable release is available from ``PyPi``::

    pip install aiida-nwchem


1b. Development Version
-----------------------

Use the following commands to obtain the latest development version::

    git clone https://github.com/aiidateam/aiida-nwchem .
    cd aiida-nwchem
    pip install -e .  # also installs aiida, if missing (but not postgres)
    #pip install -e .[pre-commit,testing] # install extras for more features
    reentry scan


2. Validate
+++++++++++
Check if the plugin is registered with::

    verdi calculation plugins


3. Setup code
+++++++++++++

Then use ``verdi code setup`` with the ``nwchem`` input plugin
to set up an AiiDA code for use with aiida-nwchem.
