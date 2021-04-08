from aiida import load_profile, orm
from aiida.plugins import CalculationFactory, WorkflowFactory, DataFactory
from aiida.engine import submit, WorkChain, ToContext, if_, while_, append_
from aiida.common import AttributeDict

from aiida_quantumespresso.workflows.protocols.utils import ProtocolMixin
from aiida_quantumespresso.utils.mapping import prepare_process_inputs

PwCalculation = CalculationFactory('quantumespresso.pw')
PwBaseWorkChain = WorkflowFactory('quantumespresso.pw.base')


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
        spec.expose_inputs(PwBaseWorkChain, namespace='low',
            exclude=('clean_workdir','pw.structure','pw.parent_folder'),
            namespace_options={'help': 'Inputs for the `PwBaseWorkChain` for the low relax.'})
        spec.expose_inputs(PwBaseWorkChain, namespace='high',
            exclude=('clean_workdir','pw.structure','pw.parent_folder'),
            namespace_options={'required':True, 'populate_defaults': False,
                'help': 'Inputs for the `PwBaseWorkChain` for the high relax.'})
        spec.input('structure', valid_type=orm.StructureData, help='The initial structure.')
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
        spec.exit_code(401, 'ERROR_SUB_PROCESS_FAILED_LOW',
            message='the low settings failed for relax')
        spec.exit_code(402, 'ERROR_SUB_PROCESS_FAILED_HIGH',
            message='the high settings failed for relax')

    @classmethod
    def get_builder_from_protocol(
        cls, code, structure, protocol=None, overrides=None, **kwargs
    ):

        args = (code, structure, protocol)

        builder = cls.get_builder()

        low = PwBaseWorkChain.get_builder_from_protocol(*args, overrides=None, **kwargs)
        low['pw'].pop('structure',None)
        low.pop('clean_workdir',None)
        low.pw.parameters['CONTROL']['calculation'] = 'vc-relax'
        low.pw.parameters['SYSTEM']['ecutwfc'] = low.pw.parameters['SYSTEM']['ecutwfc'] * 0.8
        low.pw.parameters['SYSTEM']['ecutrho'] = low.pw.parameters['SYSTEM']['ecutrho'] * 0.8
        low.kpoints_distance = low.kpoints_distance / 0.8

        high = PwBaseWorkChain.get_builder_from_protocol(*args, overrides=None, **kwargs)
        high['pw'].pop('structure',None)
        high.pop('clean_workdir',None)
        high.pw.parameters['CONTROL']['calculation'] = 'vc-relax'

        builder.low = low
        builder.high = high
        builder.structure = structure

        return builder


    def setup(self):
        self.ctx.low_not_finished = True
        self.ctx.high_not_finished = True
        print('Finished setup')

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
