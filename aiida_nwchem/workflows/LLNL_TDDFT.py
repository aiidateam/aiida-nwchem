from aiida import load_profile, orm
from aiida.plugins import CalculationFactory, WorkflowFactory, DataFactory
from aiida.engine import submit, WorkChain, ToContext, if_, while_, append_
from aiida.common import AttributeDict

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
        spec.expose_inputs(NwchemCalculation, namespace = 'ligands',
            namespace_options={'help': 'Inputs from the NwchemCalculation for ligand only calculation.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'full',
            namespace_options={'help': 'Inputs from the NwchemCalculation for combined cage and ligands calculation.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'uhf',
            namespace_options={'help': 'Inputs from the NwchemCalculation for full with UHF settings.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'dft',
            namespace_options={'help': 'Inputs from the NwchemCalculation for dft calculation.'})
        spec.expose_inputs(NwchemCalculation, namespace = 'tddft',
            namespace_options={'help': 'Inputs from the NwchemCalculation for tddft calculation.'})

        spec.outline(
            cls.setup,
            while_(cls.low_not_finished)(
                cls.run_low,
                cls.check_low,
            ),
            while_(cls.high_not_finished)(
                cls.run_high,
                cls.check_high
            ),
            cls.results,
        )
        spec.expose_outputs(PwBaseWorkChain)
        spec.exit_code(401, 'NO_CHARGE_SPECIFIED',
            message='must specify a charge for the builder')
        spec.exit_code(402, 'NO_ATOM_FOUND',
            message='no atoms found when parsing structure for elements other than "H" and "O"')
        spec.exit_code(403, 'TOO_MANY_ATOMS_FOUND',
            message='found more than one atom in structure when parsing for cage calculation')

    @classmethod
    def get_builder_from_protocol(
        cls, code, structure, charge=None, cage_style='octahedra', overrides=None, **kwargs
    ):

        if charge == None:
            return self.exit_codes.NO_CHARGE_SPECIFIED

        args = (code, structure)

        builder = cls.get_builder()

        cage = cls.get_builder()
        ligand = cls.get_builder()
        full = cls.get_builder()
        uhf = cls.get_builder()
        dft = cls.get_builder()
        tddft = cls.get_builder()

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
            return self.exit_codes.NO_ATOM_FOUND
        elif len(cage_structure.sites) > 1:
            return self.exit_codes.TOO_MANY_ATOMS_FOUND
        else:
            cage.structure = cage_structure
            ligand.structure = ligand_structure
            
        # Setup cage charge based on cage_style
        cage_charge = get_cage_charge(charge,cage_style)
        point_charges = get_point_charges(cage_style,cage_pos)

        # Setup caged parameters
        Dict = DataFactory('dict')
        cage.parameters = Dict(dict={
            'basis spherical':{
                'H' : 'library aug-cc-pVDZ',
                'O' : 'library aug-cc-pVDZ',
                cage_kind : 'library LANL08+'
            }
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
        }

        ligand.parameters = Dict(dict={
            'basis spherical':{
                'H' : 'library aug-cc-pVDZ',
                'O' : 'library aug-cc-pVDZ',
                cage_kind : 'library LANL08+'
            }
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
        }
        
        # Setup full calculation information
        full.structure = structure
        full.parameters = Dict(dict={
            'basis spherical':{
                'H' : 'library aug-cc-pVDZ',
                'O' : 'library aug-cc-pVDZ',
                cage_kind : 'library LANL08+'
            }
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
        }
           
        # Setup full calculation with UHF
        uhf.parameters = Dict(dict={
            'scf' : {
                'vectors' : 'input hf.movecs output uhf.movecs',
                'triplet; uhf' : ''
                'maxiter' : 100
            },
            'task' : 'scf energy'
        }    
        
        # DFT parameters
        dft.parameters = Dict(dict={
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
        }    

        # TDDFT parameters
        tddft.parameters = Dict(dict={
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
        }    

        builder.cage = cage
        builder.ligand = ligand
        builder.full = full
        builder.uhf = uhf
        builder.dft = dft
        builder.tddft = tddft
        builder.structure = structure

        return builder

    def get_cage_charge(self,charge,cage_style):
        
        if cage_style == 'octahedra':
            return charge - 6

    def get_point_charges(self,cage_style,position):

        point_charges = []

        if cage_style == 'octahedra':
            
            point_charges.append(np.array(position) + np.array([2,0,0]))
            point_charges.append(np.array(position) + np.array([0,2,0]))
            point_charges.append(np.array(position) + np.array([0,0,2]))
            point_charges.append(np.array(position) + np.array([-2,0,0]))
            point_charges.append(np.array(position) + np.array([0,-2,0]))
            point_charges.append(np.array(position) + np.array([0,0,-2]))

        return point_charges

    def low_not_finished(self):
 
        return self.ctx.low_not_finished

    def high_not_finished(self):
 
        return self.ctx.high_not_finished

    def run_low(self):

        inputs = AttributeDict(self.exposed_inputs(PwBaseWorkChain,'low'))
        inputs.pw.structure = self.inputs.structure

        inputs.metadata.call_link_label = 'low'
        inputs = prepare_process_inputs(PwBaseWorkChain, inputs)

        future = self.submit(PwBaseWorkChain, **inputs)

        self.report(f'launching LOW PwBaseWorkChain<{future.pk}>')

        return ToContext(workchain_low=future)

    def check_low(self):

        workchain = self.ctx.workchain_low
        if not workchain.is_finished_ok:
            self.report(f'Relax PwBaseWorkChain failed with exit status {workchain.exit_status}')
            return self.exit_codes.ERROR_SUB_PROCESS_FAILED_LOW

        self.ctx.low_not_finished = False

    def run_high(self):

        workchain = self.ctx.workchain_low

        inputs = AttributeDict(self.exposed_inputs(PwBaseWorkChain, 'high'))
        inputs.pw.structure = workchain.outputs.output_structure

        inputs.metadata.call_link_label = 'high'
        inputs = prepare_process_inputs(PwBaseWorkChain, inputs)

        future = self.submit(PwBaseWorkChain, **inputs)

        self.report(f'launching HIGH PwBaseWorkChain<{future.pk}>')

        return ToContext(workchain_high=future)

    def check_high(self):

        workchain = self.ctx.workchain_high
        if not workchain.is_finished_ok:
            self.report(f'Relax PwBaseWorkChain failed with exit status {workchain.exit_status}')
            return self.exit_codes.ERROR_SUB_PROCESS_FAILED_HIGH

        self.ctx.high_not_finished = False

    def results(self):

        workchain = self.ctx.workchain_high
        if workchain.is_finished_ok:
            self.report(f'workchain finished')

        self.out_many(self.exposed_outputs(workchain, PwBaseWorkChain))
