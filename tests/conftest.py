# -*- coding: utf-8 -*-
"""Module with test fixtures."""
import pathlib

from aiida.plugins import DataFactory
import pytest

pytest_plugins = ['aiida.manage.tests.pytest_fixtures']  # pylint: disable=invalid-name

StructureData = DataFactory('structure')


@pytest.fixture
def filepath_data():
    """Return the filepath to the ``data`` folder containing fixture data."""
    return pathlib.Path(__file__).parent / 'data'


@pytest.fixture
def nwchem_code(aiida_local_code_factory):
    """Return a code configured for the ``nwchem.nwchem`` plugin."""
    code = aiida_local_code_factory(entry_point='nwchem.nwchem',
                                    executable='nwchem')
    code.computer.set_default_mpiprocs_per_machine(1)
    return code


@pytest.fixture
def h2o():
    """Return a ``StructureData`` representing a water molecule."""
    from ase.build import molecule
    atoms = molecule('H2O', vacuum=10)
    atoms.pbc = (True, True, True)
    structure = StructureData(ase=atoms)
    return structure
