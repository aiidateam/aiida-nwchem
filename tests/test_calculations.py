# -*- coding: utf-8 -*-
"""Test NWChem calculations"""
from aiida import engine, orm, plugins
import pytest


def test_h2o(nwchem_code, h2o):
    """Test running NWChem on H2O."""
    builder = plugins.CalculationFactory('nwchem.nwchem').get_builder()
    builder.code = nwchem_code
    builder.metadata.options.resources = {'num_machines': 1}
    builder.structure = h2o
    builder.parameters = orm.Dict(dict=dict(task='dft', basis={'H': 'library sto-3g', 'O': 'library sto-3g'}))
    builder.add_cell = orm.Bool(True)

    result = engine.run(builder)

    with result['retrieved'].base.repository.open('aiida.out') as handle:
        log = handle.read()

    assert 'output_parameters' in result, log
    parameters = result['output_parameters'].get_dict()
    assert pytest.approx(parameters['total_dft_energy'], 0.1, -74.38)


def test_h2o_base(nwchem_code, filepath_data):
    """Test running NWChem on H2O using plain input file."""
    builder = plugins.CalculationFactory('nwchem.base').get_builder()
    builder.code = nwchem_code
    builder.metadata.options.resources = {'num_machines': 1}
    with open(filepath_data / 'h2o.inp', 'rb') as handle:
        builder.input_file = orm.SinglefileData(handle, filename='h2o.inp')

    result = engine.run(builder)

    with result['retrieved'].base.repository.open('aiida.out') as handle:
        log = handle.read()

    assert 'output_parameters' in result, log
    parameters = result['output_parameters'].get_dict()
    assert pytest.approx(parameters['total_dft_energy'], 0.1, -74.38)


def test_h2o_restart(nwchem_code, h2o):
    """Test restarting from a previous calculation."""
    builder = plugins.CalculationFactory('nwchem.nwchem').get_builder()
    builder.code = nwchem_code
    builder.metadata.options.resources = {'num_machines': 1}
    builder.structure = h2o
    builder.parameters = orm.Dict(dict=dict(task='dft', basis={'H': 'library sto-3g', 'O': 'library sto-3g'}))
    builder.add_cell = orm.Bool(True)
    result = engine.run(builder)
    with result['retrieved'].base.repository.open('aiida.out') as handle:
        log = handle.read()
    assert 'output_parameters' in result, log

    # now let's run a new calculation, starting from this one
    builder.restart_folder = result['remote_folder']
    result = engine.run(builder)
    with result['retrieved'].base.repository.open('aiida.out') as handle:
        log = handle.read()

    assert 'status          = restart' in log
