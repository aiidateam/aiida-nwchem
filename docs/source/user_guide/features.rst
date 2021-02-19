========
Features
========

``aiida-nwchem`` provides two main components:

    * A calculation class: ``NwchemCalculation``
    * A general parser: ``NwchemBaseParser``

The calculation class is sufficiently flexible so as to allow
almost any type of NWChem calculation to be run through ``AiiDA``.

The parser will retrieve key information from the output of the
calculation.

Currently supported are the following calculation types:

    * ``energy``
    * ``optimize``
    * ``freq``

...using any of these these theory types:

    * ``scf``
    * ``dft``
    * ``nwpw band``
    * ``tce``

Support for additional modules will be added on an ongoing basis.
If you need a particular functionality to be supported, please do
open an issue.