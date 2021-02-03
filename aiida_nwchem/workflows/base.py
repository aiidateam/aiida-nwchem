# -*- coding: utf-8 -*-
"""Base workchain to run an NWChem calculation."""

from aiida.common import AttributeDict
from aiida.engine import BaseRestartWorkChain, while_
from aiida.plugins import CalculationFactory

NwchemCalculation = CalculationFactory('nwchem.nwchem')


class NwchemBaseWorkChain(BaseRestartWorkChain):
    """Workchain to run an NWChem calculation with automated error handling and restarts."""

    _process_class = NwchemCalculation

    @classmethod
    def define(cls, spec):

        super(NwchemBaseWorkChain, cls).define(spec)
        spec.expose_inputs(NwchemCalculation, namespace='nwchem')

        spec.outline(
            cls.setup,
            while_(cls.should_run_process)(
                cls.run_process,
                cls.inspect_process,
            ),
            cls.results,
        )

        spec.expose_outputs(NwchemCalculation)

    def setup(self):
        """Call the `setup` of the `BaseRestartWorkChain` and then create the inputs dictionary in `self.ctx.inputs`.

        This `self.ctx.inputs` dictionary will be used by the `BaseRestartWorkChain` to submit the calculations in the
        internal loop.
        """

        super(NwchemBaseWorkChain, self).setup()
        self.ctx.inputs = AttributeDict(
            self.exposed_inputs(NwchemCalculation, 'nwchem'))