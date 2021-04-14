from aiida import load_profile, orm
from aiida.plugins import CalculationFactory, WorkflowFactory, DataFactory
from aiida.engine import submit, WorkChain, ToContext, if_, while_, append_
from aiida.common import AttributeDict

import numpy as np

NwchemCalculation = CalculationFactory('nwchem.nwchem')


class LLNLSpectroscopyWorkChain(WorkChain):
    """
    This work chain will contain six separate calculations.
    1) Charged atom with a cage of point charges (RHF)
    2) Ligand calculation with point charge in place of atom of interest (RHF)
    3) Full system pulling the previously computed movec files (RHF)
    4) SCF calculation with Unrestricted Hartree Fock calculation (UHF)
    5) DFT calculation including COSMO
    6) TDDFT calculation
    """ 

    @classmethod
    def define(cls,spec):
        # yapf: disable
        """
        Define the parameters and workflow
        """
        super().define(spec)
        spec.expose_inputs(NwchemCalculation, namespace = 'cage',
            namespace_options={'help': 'Inputs from the NwchemCalculation for cage calculation.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'ligand',
            namespace_options={'help': 'Inputs from the NwchemCalculation for ligand only calculation.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'full',
            namespace_options={'help': 'Inputs from the NwchemCalculation for combined cage and ligand calculation.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'uhf',
            namespace_options={'help': 'Inputs from the NwchemCalculation for full with UHF settings.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'dft',
            namespace_options={'help': 'Inputs from the NwchemCalculation for dft calculation.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'tddft',
            namespace_options={'help': 'Inputs from the NwchemCalculation for tddft calculation.'})

        spec.outline(
            cls.run_cage,
            cls.check_cage,

            cls.run_ligand,
            cls.check_ligand,

            cls.run_full,
            cls.check_full,

            cls.run_uhf,
            cls.check_uhf,

            cls.run_dft,
            cls.check_dft,

            cls.run_tddft,
            cls.check_tddft,

            cls.results,
        )
        spec.expose_outputs(NwchemCalculation)
        spec.exit_code(401, 'NO_CHARGE_SPECIFIED',
            message='must specify a charge for the builder')
        spec.exit_code(402, 'NO_ATOM_FOUND',
            message='no atoms found when parsing structure for elements other than "H" and "O"')
        spec.exit_code(403, 'TOO_MANY_ATOMS_FOUND',
            message='found more than one atom in structure when parsing for cage calculation')
        spec.exit_code(404, 'CAGE_FAILED',
            message='cage calculation failed')
        spec.exit_code(405, 'LIGAND_FAILED',
            message='ligand calculation failed')
        spec.exit_code(406, 'FULL_FAILED',
            message='full calculation failed')
        spec.exit_code(407, 'UHF_FAILED',
            message='uhf calculation failed')
        spec.exit_code(408, 'DFT_FAILED',
            message='dft calculation failed')
        spec.exit_code(409, 'TDDFT_FAILED',
            message='tddft calculation failed')

    @classmethod
    def get_builder_from_protocol(
        cls, code, structure, charge=None, cage_style='octahedra', overrides=None, **kwargs
    ):

        if charge == None:
            return cls.exit_codes.NO_CHARGE_SPECIFIED

        args = (code, structure)

        builder = cls.get_builder()

        # Find which atom
        StructureData = DataFactory('structure')
        cage_structure = StructureData()
        ligand_structure = StructureData()
        for site in structure.sites:
            site_dict = site.get_raw()
            kind = site_dict['kind_name']
            pos = site_dict['position']
            if kind != 'H' and kind != 'O':
                cage_kind = kind
                cage_pos = pos
                cage_structure.append_atom(symbols=kind,position=pos)
                ligand_charge = [[pos[0],pos[1],pos[2],charge]]
            elif kind == 'H' or kind == 'O':
                ligand_structure.append_atom(symbols=kind,position=pos)

        # Check that there is only one atom
        if len(cage_structure.sites) < 1:
            return cls.exit_codes.NO_ATOM_FOUND
        elif len(cage_structure.sites) > 1:
            return cls.exit_codes.TOO_MANY_ATOMS_FOUND
        else:
            builder.cage.structure = cage_structure
            builder.ligand.structure = ligand_structure
            
        # Setup cage charge based on cage_style
        cage_charge = cls.get_cage_charge(charge,cage_style)
        point_charges = cls.get_point_charges(cage_style,cage_pos)

        # Setup default metadata
        Dict = DataFactory('dict')
        metadata = {
            'options' : {
                'resources' : {
                    'num_machines' : 4
                },
                'max_wallclock_seconds' : 30*60,
                'queue_name' : 'pdebug',
                'account' : 'corrctl'
            }
        }
 

        # Setup caged parameters
        builder.cage.code = code
        builder.cage.metadata = metadata
        builder.cage.parameters = Dict(dict={

            'basis spherical':{
                'H' : 'library aug-cc-pVDZ',
                'O' : 'library aug-cc-pVDZ',
                cage_kind : 'library LANL08+'
            },

            'set':{
                'tolguess': 1e-9
             },

            'charge' : cage_charge,

            'point_charges' : point_charges,

            'scf' : {
                'triplet':'',
                'maxiter' : 100,
                'vectors' : 'atomic output {0}.movecs'.format(cage_kind.lower())
            },

            'task' : 'scf energy'
        })

        builder.ligand.code = code
        builder.ligand.metadata = metadata
        builder.ligand.parameters = Dict(dict={
            'basis spherical':{
                'H' : 'library aug-cc-pVDZ',
                'O' : 'library aug-cc-pVDZ',
                cage_kind : 'library LANL08+'
            },
            'set':{
                'tolguess': 1e-9
             },
            'charge' : charge,
            'point_charges' : ligand_charge,
            'scf' : {
                'singlet':'',
                'maxiter' : 100,
                'vectors' : 'atomic output ligand.movecs'
            },
            'task' : 'scf energy'
        })
        
        # Setup full calculation information
        builder.full.code = code
        builder.full.metadata = metadata
        builder.full.structure = structure
        builder.full.parameters = Dict(dict={
            'basis spherical':{
                'H' : 'library aug-cc-pVDZ',
                'O' : 'library aug-cc-pVDZ',
                cage_kind : 'library LANL08+'
            },
            'set':{
                'tolguess': 1e-9
             },
            'charge' : charge,
            'scf' : {
                'triplet':'',
                'maxiter' : 100,
                'vectors' : 'input fragment {0}.movecs ligand.movecs output hf.movecs'.format(cage_kind.lower())
            },
            'task' : 'scf energy'
        })
           
        # Setup full calculation with UHF
        builder.uhf.code = code
        builder.uhf.metadata = metadata
        builder.uhf.structure = structure
        builder.uhf.parameters = Dict(dict={
            'restart' : True,
            'scf' : {
                'vectors' : 'input hf.movecs output uhf.movecs',
                'triplet; uhf' : '',
                'maxiter' : 100
            },
            'task' : 'scf energy'
        })    
        
        # DFT parameters
        builder.dft.code = code
        builder.dft.metadata = metadata
        builder.dft.structure = structure
        builder.dft.parameters = Dict(dict={
            'restart' : True,
            'driver' : {
                'maxiter' : 500
            },
            'cosmo' : {
                'dielec' : 78.0,
                'rsolv' : 0.50
            },
            'dft' : {
                'iterations' : 500,
                'xc' : 'xbnl07 0.90 lyp 1.00 hfexch 1.00',
                'cam 0.33 cam_alpha 0.0 cam_beta 1.0' : '',
                'direct' : '',
                'vectors' : 'input uhf.movecs output dft.movecs',
                'mult' : 3,
                'mulliken' : ''
            },
            'task' : 'dft energy'
        })   

        # TDDFT parameters
        builder.tddft.code = code
        builder.tddft.metadata = metadata
        builder.tddft.structure = structure
        builder.tddft.parameters = Dict(dict={
            'restart' : True,
            'dft' : {
                'iterations' : 500,
                'xc' : 'xbnl07 0.90 lyp 1.00 hfexch 1.00',
                'cam 0.33 cam_alpha 0.0 cam_beta 1.0' : '',
                'direct' : '',
                'vectors' : 'input uhf.movecs output dft.movecs',
                'mult' : 3,
                'mulliken' : ''
            },
            'tddft' : {
                'cis' : '',
                'NOSINGLET' : '',
                'nroots' : 20,
                'maxiter' : 1000,
                'freeze' : 17
            },
            'task' : 'tddft energy'
        })   

        return builder

    def get_cage_charge(charge,cage_style):
        
        if cage_style == 'octahedra':
            return charge - 6

    def get_point_charges(cage_style,position):

        point_charges = []

        if cage_style == 'octahedra':
            
            point_charges.append((np.array(position) + np.array([2,0,0])).tolist() + [-1])
            point_charges.append((np.array(position) + np.array([0,2,0])).tolist() + [-1])
            point_charges.append((np.array(position) + np.array([0,0,2])).tolist() + [-1])
            point_charges.append((np.array(position) + np.array([-2,0,0])).tolist() + [-1])
            point_charges.append((np.array(position) + np.array([0,-2,0])).tolist() + [-1])
            point_charges.append((np.array(position) + np.array([0,0,-2])).tolist() + [-1])

        return point_charges

    def run_cage(self):

        inputs = AttributeDict(self.exposed_inputs(NwchemCalculation,'cage'))
        parameters = self.inputs.cage.parameters.get_dict()
        inputs.metadata = self.inputs.cage.metadata
        inputs.metadata.call_link_label = 'cage'
        inputs.code = self.inputs.cage.code
        inputs.parameters = orm.Dict(dict=parameters)
        inputs.structure = self.inputs.cage.structure

        future_cage = self.submit(NwchemCalculation,**inputs)
        self.report(f'launching cage NwchemCalculation <{future_cage.pk}>')
        return ToContext(calc_cage=future_cage)

    def check_cage(self):

        calculation = self.ctx.calc_cage

        if not calculation.is_finished_ok:
            self.report(f'cage NwchemCalculation failed with exit status {calculation.exit_status}')
            return self.exit_codes.CAGE_FAILED

        self.ctx.calc_parent_folder = calculation.outputs.remote_folder

    def run_ligand(self):

        inputs = AttributeDict(self.exposed_inputs(NwchemCalculation,'ligand'))
        inputs.parent_folder = self.ctx.calc_parent_folder
        parameters = self.inputs.ligand.parameters.get_dict()
        inputs.metadata = self.inputs.ligand.metadata
        inputs.metadata.call_link_label = 'ligand'
        inputs.parameters = orm.Dict(dict=parameters)
        inputs.structure = self.inputs.ligand.structure

        future_ligand = self.submit(NwchemCalculation,**inputs)
        self.report(f'launching ligand NwchemCalculation <{future_ligand.pk}>')
        return ToContext(calc_ligand=future_ligand)

    def check_ligand(self):

        calculation = self.ctx.calc_ligand

        if not calculation.is_finished_ok:
            self.report(f'ligand NwchemCalculation failed with exit status {calculation.exit_status}')
            return self.exit_codes.LIGAND_FAILED

        self.ctx.calc_parent_folder = calculation.outputs.remote_folder

    def run_full(self):

        inputs = AttributeDict(self.exposed_inputs(NwchemCalculation,'full'))
        inputs.parent_folder = self.ctx.calc_parent_folder
        parameters = self.inputs.full.parameters.get_dict()
        inputs.metadata = self.inputs.full.metadata
        inputs.metadata.call_link_label = 'full'
        inputs.parameters = orm.Dict(dict=parameters)
        inputs.structure = self.inputs.full.structure

        future_full = self.submit(NwchemCalculation,**inputs)
        self.report(f'launching cage NwchemCalculation <{future_full.pk}>')
        return ToContext(calc_full=future_full)

    def check_full(self):

        calculation = self.ctx.calc_full

        if not calculation.is_finished_ok:
            self.report(f'full NwchemCalculation failed with exit status {calculation.exit_status}')
            return self.exit_codes.FULL_FAILED

        self.ctx.calc_parent_folder = calculation.outputs.remote_folder

    def run_uhf(self):

        inputs = AttributeDict(self.exposed_inputs(NwchemCalculation,'uhf'))
        inputs.parent_folder = self.ctx.calc_parent_folder
        parameters = self.inputs.uhf.parameters.get_dict()
        inputs.metadata = self.inputs.uhf.metadata
        inputs.metadata.call_link_label = 'uhf'
        inputs.parameters = orm.Dict(dict=parameters)
        inputs.structure = self.inputs.uhf.structure

        future_uhf = self.submit(NwchemCalculation,**inputs)
        self.report(f'launching uhf NwchemCalculation <{future_uhf.pk}>')
        return ToContext(calc_uhf=future_uhf)

    def check_uhf(self):

        calculation = self.ctx.calc_uhf

        if not calculation.is_finished_ok:
            self.report(f'uhf NwchemCalculation failed with exit status {calculation.exit_status}')
            return self.exit_codes.UHF_FAILED

        self.ctx.calc_parent_folder = calculation.outputs.remote_folder

    def run_dft(self):

        inputs = AttributeDict(self.exposed_inputs(NwchemCalculation,'dft'))
        inputs.parent_folder = self.ctx.calc_parent_folder
        parameters = self.inputs.dft.parameters.get_dict()
        inputs.metadata = self.inputs.dft.metadata
        inputs.metadata.call_link_label = 'dft'
        inputs.parameters = orm.Dict(dict=parameters)
        inputs.structure = self.inputs.dft.structure

        future_dft = self.submit(NwchemCalculation,**inputs)
        self.report(f'launching dft NwchemCalculation <{future_dft.pk}>')
        return ToContext(calc_dft=future_dft)
 
    def check_dft(self):

        calculation = self.ctx.calc_dft

        if not calculation.is_finished_ok:
            self.report(f'dft NwchemCalculation failed with exit status {calculation.exit_status}')
            return self.exit_codes.DFT_FAILED

        self.ctx.calc_parent_folder = calculation.outputs.remote_folder

    def run_tddft(self):

        inputs = AttributeDict(self.exposed_inputs(NwchemCalculation,'tddft'))
        inputs.parent_folder = self.ctx.calc_parent_folder
        parameters = self.inputs.tddft.parameters.get_dict()
        inputs.metadata = self.inputs.tddft.metadata
        inputs.metadata.call_link_label = 'tddft'
        inputs.parameters = orm.Dict(dict=parameters)
        inputs.structure = self.inputs.dft.structure

        future_tddft = self.submit(NwchemCalculation,**inputs)
        self.report(f'launching tddft NwchemCalculation <{future_tddft.pk}>')
        return ToContext(calc_tddft=future_tddft)

    def check_tddft(self):

        calculation = self.ctx.calc_tddft

        if not calculation.is_finished_ok:
            self.report(f'tddft NwchemCalculation failed with exit status {calculation.exit_status}')
            return self.exit_codes.TDDFT_FAILED

    def results(self):

        calculation = self.ctx.calc_tddft
        if calculation.is_finished_ok:
            self.report(f'workchain finished')

        self.out_many(self.exposed_outputs(calculation, NwchemCalculation))
