# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida_core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""
Tests for the NWChem input plugins.
"""

from aiida import orm
from aiida.orm.nodes.data.structure import has_ase, has_pymatgen
import pytest

from aiida_nwchem.calculations.nwcpymatgen import \
    _prepare_pymatgen_dict  # pylint: disable=import-error,no-name-in-module


@pytest.mark.skipif(not has_ase(), 'Unable to import ase')
@pytest.mark.skipif(not has_pymatgen(), 'Unable to import pymatgen')
def test_input_pymatgen():
    """Test that pymatgen input generator works as expected."""
    from ase import Atoms

    par = {
        'directives': [['set nwpw:minimizer', '2'],
                       ['set nwpw:psi_nolattice', '.true.'],
                       ['set includestress', '.true.']],
        'geometry_options':
        ['units', 'au', 'center', 'noautosym', 'noautoz', 'print'],
        'memory_options': [],
        'symmetry_options': [],
        'tasks': [{
            'alternate_directives': {
                'driver': {
                    'clear': '',
                    'maxiter': 40
                },
                'nwpw': {
                    'ewald_ncut': 8,
                    'simulation_cell': '\n  ngrid 16 16 16\n end'
                }
            },
            'basis_set': {},
            'basis_set_option': 'cartesian',
            'charge': 0,
            'operation': 'optimize',
            'spin_multiplicity': None,
            'theory': 'pspw',
            'theory_directives': {},
            'title': None
        }]
    }

    atoms = Atoms(['Si', 'Si', 'Si', 'Si', 'C', 'C', 'C', 'C'],
                  cell=[8.277, 8.277, 8.277])
    atoms.set_scaled_positions([
        (-0.5, -0.5, -0.5),
        (0.0, 0.0, -0.5),
        (0.0, -0.5, 0.0),
        (-0.5, 0.0, 0.0),
        (-0.25, -0.25, -0.25),
        (0.25, 0.25, -0.25),
        (0.25, -0.25, 0.25),
        (-0.25, 0.25, 0.25),
    ])
    structure = orm.StructureData(ase=atoms)

    ## Test 1
    # Input file string prodiced by pymatgen
    app = _prepare_pymatgen_dict(par, structure)
    # Target input file
    target_string = '''set nwpw:minimizer 2
set nwpw:psi_nolattice .true.
set includestress .true.
geometry units au center noautosym noautoz print
 Si -4.1385 -4.1385 -4.1385
 Si 0.0 0.0 -4.1385
 Si 0.0 -4.1385 0.0
 Si -4.1385 0.0 0.0
 C -2.06925 -2.06925 -2.06925
 C 2.06925 2.06925 -2.06925
 C 2.06925 -2.06925 2.06925
 C -2.06925 2.06925 2.06925
end

title "pspw optimize"
charge 0
basis cartesian

end
driver
 clear \n maxiter 40
end
nwpw
 ewald_ncut 8
 simulation_cell \n  ngrid 16 16 16
 end
end
task pspw optimize
'''
    assert app == target_string

    ## Test 2
    par['add_cell'] = True

    # Input file string prodiced by pymatgen
    app = _prepare_pymatgen_dict(par, structure)
    # Target input file
    target_string = '''set nwpw:minimizer 2
set nwpw:psi_nolattice .true.
set includestress .true.
geometry units au center noautosym noautoz print \n  system crystal
    lat_a 8.277
    lat_b 8.277
    lat_c 8.277
    alpha 90.0
    beta  90.0
    gamma 90.0
  end
 Si -0.5 -0.5 -0.5
 Si 0.0 0.0 -0.5
 Si 0.0 -0.5 0.0
 Si -0.5 0.0 0.0
 C -0.25 -0.25 -0.25
 C 0.25 0.25 -0.25
 C 0.25 -0.25 0.25
 C -0.25 0.25 0.25
end

title "pspw optimize"
charge 0
basis cartesian

end
driver
 clear \n maxiter 40
end
nwpw
 ewald_ncut 8
 simulation_cell \n  ngrid 16 16 16
 end
end
task pspw optimize
'''
    assert app == target_string
