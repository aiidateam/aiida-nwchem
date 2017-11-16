# -*- coding: utf-8 -*-

from aiida.backends.testbase import AiidaTestCase

class FakeObject(object):
    """
    A wrapper for dictionary, which can be used instead of object.
    Example use case: fake Calculation object ``calc``, having keys
    ``inp`` and ``out`` to access also fake NodeInputManager and
    NodeOutputManager.
    """

    def __init__(self, dictionary):
        self._dictionary = dictionary

    def __getattr__(self, name):
        if isinstance(self._dictionary[name], dict):
            return FakeObject(self._dictionary[name])
        else:
            return self._dictionary[name]

class TestTcodDbExporter(AiidaTestCase):

    def test_nwcpymatgen_translation(self):
        from aiida.common.pluginloader import get_plugin
        from aiida.orm.data.parameter import ParameterData
        from aiida.tools.dbexporters.tcod import translate_calculation_specific_values

        tcod_plugin = get_plugin('tools.dbexporters.tcod_plugins', 'nwchem.nwcpymatgen')

        calc = FakeObject({
            "out": {"output":
                ParameterData(dict={
                    "basis_set": {
                        "H": {
                            "description": "6-31g",
                            "functions": "2",
                            "shells": "2",
                            "types": "2s"
                        },
                        "O": {
                            "description": "6-31g",
                            "functions": "9",
                            "shells": "5",
                            "types": "3s2p"
                        }
                    },
                    "corrections": {},
                    "energies": [
                        -2057.99011937535
                    ],
                    "errors": [],
                    "frequencies": None,
                    "has_error": False,
                    "job_type": "NWChem SCF Module"
                }),
                "job_info": ParameterData(dict={
                    "0 permanent": ".",
                    "0 scratch": ".",
                    "argument  1": "aiida.in",
                    "compiled": "Sun_Dec_22_04:02:59_2013",
                    "data base": "./aiida.db",
                    "date": "Mon May 11 17:10:07 2015",
                    "ga revision": "10379",
                    "global": "200.0 Mbytes (distinct from heap & stack)",
                    "hardfail": "no",
                    "heap": "100.0 Mbytes",
                    "hostname": "theospc11",
                    "input": "aiida.in",
                    "nproc": "6",
                    "nwchem branch": "6.3",
                    "nwchem revision": "24277",
                    "prefix": "aiida.",
                    "program": "/usr/bin/nwchem",
                    "source": "/build/buildd/nwchem-6.3+r1",
                    "stack": "100.0 Mbytes",
                    "status": "startup",
                    "time left": "-1s",
                    "total": "400.0 Mbytes",
                    "verify": "yes",
                })
            }})
        res = translate_calculation_specific_values(calc, tcod_plugin)
        self.assertEquals(res, {
            '_tcod_software_package': 'NWChem',
            '_tcod_software_package_version': '6.3',
            '_tcod_software_package_compilation_date': '2013-12-22T04:02:59',
            '_atom_type_symbol': ['H', 'O'],
            '_dft_atom_basisset': ['6-31g', '6-31g'],
            '_dft_atom_type_valence_configuration': ['2s', '3s2p'],
        })