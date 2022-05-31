=====
Usage
=====

Preparing the input for a calculation is similar to
preparing an input file 'by-hand' for use with NWChem,
with a few exceptions.


Below we will detail how to prepare a DFT optimisation for
a small molecule.

Start by loading an AiiDA profile::

    from aiida import load_profile
    load_profile()

Find the installed `NWChem` code object in the database::

    from aiida.orm import Code
    from aiida.plugins import CalculationFactory, WorkflowFactory
    code = Code.get_from_string('nwchem')

Create a calculation instance and get a builder::

    NWChemCalculation = CalculationFactory('nwchem.nwchem')
    builder = NWChemCalculation.get_builder()

Prepare a structure in the standard way::

    # H2 guess structure
    structure = StructureData()
    structure.append_atom(position=(0.,0.,0.),symbols='H')
    structure.append_atom(position=(0.,1.,0.),symbols='H')

Prepare the parameters in the form of a nested dictionary::

    Dict = DataFactory('dict')
    parameters = Dict(dict={
        'basis': {'H': 'library 6-31g'},
        'dft':{
            'iterations': 50,
            'xc': 'xpbe96 cpbe96',
        },
        'task': 'dft optimize'
    })

For each key pair, the key is either a keyword or section name.
The value is either a value to assign to a keyword, another dictionary
in the case of a section name, or `''` in the case of a lone keyword.

.. note::
    The special keywords `basis` and `task` are defined separately from standard keywords in the
    parameter dictionary.

.. warning::
    Only one `task` or `basis` can be defined. This is both a limitation
    of a dictionary in that keys must be unique, and a design choice.
    In `AiiDA`, a central idea is provenance tracking. While it is possible
    to run many tasks sequentially in a single `NWChem` input file, only a single
    set of inputs and outputs would be captured for a single `AiiDA` process.
    Conceptually in this case, it would make more sense to separate this
    one large job into a series of smaller component jobs and to track
    the provenance fully for each. For this reason, only one `task` directive
    is allowed per job. In some cases (e.g. post Hartree-Fock calculations),
    it's necessary to supply a starting wavefunction (often HF). In this
    instance, separate `task` directives still aren't needed as the required
    task will be called internally.

Set resource options and submit to the daemon::

    builder.metadata.options.resources = {'num_machines': 1}
    builder.metadata.options.max_wallclock_seconds = 1800
    builder.code = code
    builder.structure = structure
    builder.parameters = parameters
    from aiida.engine import submit
    calc = submit(builder)

Finally, when the calculation has finished successfully, we can
retrieve the results. In this example, print the output
parameters `dict`::

    print(calc.outputs.output_parameters.get_dict())

The parsed data is printed::

    {
    'task': 'geo-opt',
    'cpu_time': '1.6',
    'wall_time': '1.6',
    'final_step': '4',
    'final_energy': {
        'charge': '0.00',
        'theory': 'dft',
        'wavefunction': 'closed shell',
        'total_dft_energy': '-1.161976599973'
        },
    'final_opt_energy': '-1.16197660'
    }


In addition to the special keywords, `task` and `basis`,
the keyword `set` is also reserved. While normally, each
dictionary key must be unique, in `NWChem`, multiple `set`
commands may be used to set special internal variables.
To facilitate this, the value of `set` may be a dictionary where
each key-value pair defines a variable and that value to set for
it::

    parameters['set'] = {
        'includestress': '.true.',
        'nwpw:zero_forces': '.true.'
    }

In addition to the `NwchemCalculation` calculation type,
the plugin includes a `workflow`, `NwchemBaseWorkflow`,
which wraps this calculation. It is used in a similar
way::

    base_workchain = WorkflowFactory('nwchem.base')
    builder = base_workchain.get_builder()

Use of this base workflow is preferred to the bare
calculation as future releases will implement restart
capability via this workflow.
