========
Examples
========

DFT optimisation for a dihydrogen molecule::

    from aiida import load_profile
    load_profile()

    from aiida.orm import Code
    from aiida.plugins import CalculationFactory, WorkflowFactory
    code = Code.get_from_string('nwchem')
    NWChemCalculation = CalculationFactory('nwchem.nwchem')

    # Gas phase
    builder = NWChemCalculation.get_builder()
    from aiida.plugins import DataFactory
    StructureData = DataFactory('core.structure')

    # H2 guess structure
    structure = StructureData()
    structure.append_atom(position=(0.,0.,0.),symbols='H')
    structure.append_atom(position=(0.,1.,0.),symbols='H')

    Dict = DataFactory('dict')
    parameters = Dict({
        'basis': {'H': 'library 6-31g'},
        'dft':{
            'iterations': 50,
            'xc': 'xpbe96 cpbe96',
        },
        'task': 'dft optimize'
    })

    builder.metadata.options.resources = {'num_machines': 1}
    builder.metadata.options.max_wallclock_seconds = 1800
    builder.code = code
    builder.structure = structure
    builder.parameters = parameters
    from aiida.engine import submit
    calc = submit(builder)

NWPW Band for bulk silicon::

    # NWPW - Si
    from aiida.orm import load_node
    si_structure = load_node(421)
    builder.structure = si_structure

    Dict = DataFactory('dict')
    parameters = Dict({
        'nwpw': {
            'xc': 'pbe96',
            'lmbfgs': 0,
            'ewald_rcut': 3.0,
            'ewald_ncut': 8,
            'monkhorst-pack': '3 3 3'
        },
        'driver':{
            'maxiter': 40,
        },
        'task': 'band optimize'
    })
    builder.add_cell = Bool(True)  # Insert the unit cell

    builder.metadata.options.resources = {'num_machines': 1}
    builder.metadata.options.max_wallclock_seconds = 1800
    builder.metadata.options.total_memory = 5000.
    builder.code = code
    # builder.structure = structure
    builder.parameters = parameters
    from aiida.engine import submit
    calc = submit(builder)


Base workflow with NWPW Band::

    # Test base workflow
    base_workchain = WorkflowFactory('nwchem.base')
    builder = base_workchain.get_builder()

    # NWPW
    from aiida.plugins import DataFactory
    StructureData = DataFactory('core.structure')
    alat = 4. # angstrom
    cell = [[alat, 0., 0.,],
            [0., alat, 0.,],
            [0., 0., alat,],
        ]
    # BaTiO3 cubic structure
    structure = StructureData(cell=cell)
    structure.append_atom(position=(0.,0.,0.),symbols='Ba')
    structure.append_atom(position=(alat/2.,alat/2.,alat/2.),symbols='Ti')
    structure.append_atom(position=(alat/2.,alat/2.,0.),symbols='O')
    structure.append_atom(position=(alat/2.,0.,alat/2.),symbols='O')
    structure.append_atom(position=(0.,alat/2.,alat/2.),symbols='O')


    Dict = DataFactory('dict')
    parameters = Dict({
        'nwpw': {
            'xc': 'pbe96',
        },
        'task': 'band energy'
    })

    builder.nwchem.metadata.options.resources = {'num_machines': 1}
    builder.nwchem.metadata.options.max_wallclock_seconds = 1800
    builder.nwchem.code = code
    builder.nwchem.structure = structure
    builder.nwchem.parameters = parameters
    from aiida.engine import submit
    calc = submit(builder)



CCSDT via TCE::

    # TCE
    from aiida.plugins import DataFactory
    StructureData = DataFactory('core.structure')

    # H2 structure
    structure = StructureData()
    structure.append_atom(position=(0.,0.,0.),symbols='H')
    structure.append_atom(position=(0.,1.,0.),symbols='H')

    Dict = DataFactory('dict')
    parameters = Dict({
        'basis': {'*': 'library cc-pvtz'},
        'symmetry': 'c1',
        'charge': 0,
        'scf': {
            'thresh': 1.0e-8,
            'tol2e': 1e-10,
            'rhf': '',
            'maxiter': 100,
            'singlet': ''
        },
        'tce': {
            'ccsdt' :'',
            'tilesize': 20,
            'attilesize': 40,
            '2eorb': '',
            '2emet': 13,
            'thresh': 1.0e-06,
        },
        'set': {
            'tce:nts': 'T',
            'tce:xmem' : 400,
        },
        'task': 'tce energy'
    })

    builder.metadata.options.resources = {'num_machines': 1}
    builder.metadata.options.max_wallclock_seconds = 1800
    builder.code = code
    builder.structure = structure
    builder.parameters = parameters
    from aiida.engine import submit
    calc = submit(builder)
