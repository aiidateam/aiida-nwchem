# -*- coding: utf-8 -*-
"""Test NWChem calculations"""
import pytest
from aiida import engine, orm, plugins

def test_h2o(nwchem_code, h2o):
    """Test running NWChem on H2O."""
    builder = plugins.CalculationFactory('nwchem.nwchem').get_builder()
    builder.code = nwchem_code

    # builder.metadata.options.max_wallclock_seconds = 60
    builder.metadata.options.resources = {'num_machines': 1}
    builder.structure = h2o
    builder.parameters = orm.Dict(dict=dict(task='dft',
                                            basis={
                                                'H': 'library sto-3g',
                                                'O': 'library sto-3g'
                                            }))
    builder.add_cell = orm.Bool(True)

    result = engine.run(builder)

    with result['retrieved'].open('aiida.out') as handle:
        log = handle.read()

    assert 'output_parameters' in result, log
    parameters = result['output_parameters'].get_dict()
    assert pytest.approx(parameters['total_dft_energy'], 0.1, -74.38)
