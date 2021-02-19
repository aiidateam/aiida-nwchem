# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida_core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
from __future__ import absolute_import

import os
import tempfile

from ase import Atoms
import numpy as np
import re

from aiida.parsers import Parser
from aiida.common import OutputParsingError, NotExistent
from aiida.engine import ExitCode
from aiida import orm

from aiida.plugins import CalculationFactory

NwchemCalculation = CalculationFactory('nwchem.nwchem')


class NwchemBaseParser(Parser):
    """
    Base parser for NWChem calculations.

    The goal for the standard parser is to parse all standard
    NWChem modules.

    Currently supported modules:
    - SCF
    - DFT
    - Geo-opt
    - Frequency analysis

    Multiple tasks are possible so we must parse each one.
    To simplify providence, only one task directive is allowed.

    The output will be parameter data containing a list
    of dictionaries in the order of the tasks.
    """
    def __init__(self, node):
        """
        Initialize parser instance and check that node passed is
        from an NWChem calculation.
        """
        from aiida.common import exceptions
        super(NwchemBaseParser, self).__init__(node)
        if not issubclass(node.process_class, NwchemCalculation):
            raise exceptions.ParsingError("Can only parse NWChem calculations")

    def parse(self, **kwargs):
        """
        Parse retrieved file
        """
        from aiida.orm import SinglefileData

        output_filename = self.node.get_option('output_filename')

        # Check that folder content is as expected
        files_retrieved = self.retrieved.list_object_names()
        files_expected = [output_filename]
        # Note: set(A) <= set(B) checks whether A is a subset of B
        if not set(files_expected) <= set(files_retrieved):
            self.logger.error("Found files '{}', expected to find '{}'".format(
                files_retrieved, files_expected))
            return self.exit_codes.ERROR_MISSING_OUTPUT_FILES

        # Read output file
        self.logger.info("Parsing '{}'".format(output_filename))
        with self.retrieved.open(output_filename, 'r') as fhandle:
            all_lines = [line.strip('\n') for line in fhandle.readlines()]

        # Check if NWChem finished:
        #TODO: Handle the case of the 'ignore' keyword
        if not re.search(r'^\sTotal times  cpu:', all_lines[-1]):
            return self.exit_codes.ERROR_OUTPUT_STDOUT_INCOMPLETE

        # In either case try to parse
        # Cut the data into lists
        task_list = self.separate_tasks(all_lines)
        # Parsing of only one task type is permitted, although many may be detected
        # if len(task_types) > 1 :
        #     return self.exit_codes.ERROR_MULTIPLE_CALCULATIONS
        if len(task_list) == 0: # Nothing that we are able to parse
            return self.exit_codes.ERROR_OUTPUT_STDOUT_INCOMPLETE

        # Parse only the final task
        task = task_list[-1]
        task_type = task['task_type']
        theory_type = task['theory_type']
        task_lines = task['lines']
        module_parser = getattr(self, 'parse_'+task_type)
        module_parser(task_lines, theory_type)

        return ExitCode(0)

    def parse_errors(self, all_lines, err_index):
        """
        Parse the specific error messages

        args: all_lines: list of lines from outfile, stripped of newline char
        returns: error_dict: dictionary describing the error encountered
        """

        # Limit the search to lines we've seen already
        lines=all_lines[:err_index]

        error_lines = []

        state = None
        info = ""

        # Read the lines backwards from index looking for info between '-----'
        for index in range(len(lines)-1, 0, -1):
            line = lines[index]

            if state == 'error_info':
                if re.match(r'^\s-+$', line):
                    error_lines.append(info)
                    info = ""
                    state = None
                    continue
                else:
                    info = line + info # Order important because we looping backwards
                    continue
            else:
                if re.match(r'^\s-+$', line):
                    state = 'error_info'
                    continue
                #else:
                #    break

        # Organise and clean the data a bit
        # Clean up to do
        error_dict = {}
        error_dict['error'] = error_lines[2]
        error_dict['line'] = error_lines[1]
        error_dict['explanation'] = error_lines[0]

        return error_dict

    def separate_tasks(self, all_lines):
        """
        Slice the stdout in to sections according to the module used.
        Returns a list of the tasks parsed and a list of lists containing
        lines from each task
        """


        # State to track if we're in a task or not
        in_task = False
        # List to hold all of the parsed task dictionaries
        task_list = []

        for index, line in enumerate(all_lines):

            # Check for errors:
            if re.search('For more information see the NWChem manual', line):
                self.parse_errors(all_lines, index)
                #raise OutputParsingError("NWChem did not finish properly. Reported error:\n"
                #                         "{}".format(line))

            if re.match(r'^\s*NWChem Input Module\s*$', line):
                # We're inside a task block
                in_task = True
                first_line = index
                task_dict = {
                    'task_type': None, # We do not know the task type yet
                    'theory_type': None, # We also do not yet know the theory used
                    'lines': [],
                }

                continue

            if in_task:
                # Determine what general kind of task we have - e.g. energy, optimisation, etc.
                if re.match(r'^\s*NWChem Geometry Optimization\s*$',line):
                    task_dict['task_type'] = 'geoopt'
                    continue
                elif re.match(r'^\s*NWChem Nuclear Hessian and Frequency Analysis\s*$',line):
                    task_dict['task_type'] = 'freq'
                    continue

                # Determine the theory used - eg. HF, DFT, etc.
                if re.match(r'^\s*NWChem SCF Module\s*$',line):
                    task_dict['theory_type'] = 'scf'
                    continue
                elif re.match(r'^\s*NWChem DFT Module\s*$',line):
                    task_dict['theory_type'] = 'dft'
                    continue
                elif re.match(r'^[\s\*]*NWPW BAND Calculation[\s\*]*$',line):
                    task_dict['theory_type'] = 'nwpw_band'
                    continue
                elif re.match(r'^[\s]+NWChem Extensible Many-Electron Theory Module[\s]*$', line):
                    task_dict['theory_type'] = 'tce'
                    continue

                # Check if we've hit the end of the task block
                if re.match(r'^ Task  times  cpu:\s+[0-9.]+s\s+wall:\s+[0-9.]+s$', line):
                    in_task = False
                    # If we didn't find a task, then this must be an energy type calculation (or another that we do not support!)
                    if task_dict['task_type'] is None:
                        task_dict['task_type'] = 'energy'
                    last_line = index
                    task_dict['lines'] = all_lines[first_line:last_line+1]
                    task_list.append(task_dict)

                # If we're really finished, return the task list:
                    if re.match(r'^\s+CITATION\s+$', line):
                        break

        return task_list


    def parse_scf(self,lines):
        """
        Parse an SCF (i.e. HF) task block

        args: lines: the lines to parse
        """

        result_dict = {'theory': 'scf'}
        state = None

        for line in lines:

            result = re.match(r'^\s*wavefunction\s*=\s*([A-Z]+)\s*$',line)
            if result:
                result_dict['wavefunction'] = result.group(1)

            if re.match(r'^\s*Final [ROU]+HF\s*results\s*$',line):
                state = 'final-results'
            if state == 'final-results':
                result = re.match(r'^\s*([^=]+?)\s*=\s*([\-\d\.]+)$',line)
                if result:
                    key = re.sub(r'[^a-zA-Z0-9]+', '_', result.group(1).lower())
                    result_dict[key] = result.group(2)

            # End of task
            if re.match('^ Task  times  cpu:', line):
                result = re.match(r'^ Task  times  cpu:\s*([\d\.\d]+)s\s*wall:\s*([\d\.\d]+)s', line)
                result_dict['cpu_time'] = result.group(1)
                result_dict['wall_time'] = result.group(2)
                break

        return result_dict


    def parse_dft(self, lines):
        """
        Parse a DFT task block

        args: lines: the lines to parse
        """

        result_dict = {'theory':'dft'}
        state = None

        for line in lines:

            result = re.match(r'\s*Wavefunction type:\s*([A-z\s]*).\s*$',line)
            if result:
                result_dict['wavefunction'] = result.group(1)

            # Note the search for the Total DFT energy. NWChem doesn't otherwise
            # announce that the results are being printed.
            if re.match(r'^\s*Total DFT energy', line):
                state = 'final-results'
            if state == 'final-results':
                result = re.match(r'^\s*([^=]+?)\s*=\s*([\-\d\.]+)$',line)
                if result:
                    key = re.sub(r'[^a-zA-Z0-9]+', '_', result.group(1).lower())
                    result_dict[key] = result.group(2)

            # End of task
            if re.match('^ Task  times  cpu:', line):
                result = re.match(r'^ Task  times  cpu:\s*([\d\.\d]+)s\s*wall:\s*([\d\.\d]+)s', line)
                result_dict['cpu_time'] = result.group(1)
                result_dict['wall_time'] = result.group(2)
                break

        return result_dict


    def parse_nwpw_band(self, lines):
        """
        Parse an 'NWPW Band' task block

        args: lines: the lines to parse
        """
        result_dict = {'theory': 'nwpw band'}
        state = None
        forces = []

        for line in lines:

            result = re.match(r'^\s*electron spin\s*=\s*([A-z]+)\s*$',line)
            if result:
                result_dict['electron spin'] = result.group(1)

            # Find start of results section
            if re.match(r'^[\s=]*summary of results[\s=]*$', line):
                state = 'final-results'

            # Gather energies
            if state == 'final-results':
                result = re.match(r'^\s*([A-z\s.-]+)[\s:]+([0-9.E+-]+)\s*\([0-9a-zA-Z.+\/\s-]*\)\s*$',line)
                if result:
                    key = re.sub(r'[^a-zA-Z0-9]+', '_', result.group(1).strip().lower())
                    result_dict[key] = float(result.group(2))

            # Forces
            result = re.match(r'^\s+[0-9]+[\sA-z\(]+([0-9\-.]+)\s+([0-9\-.]+)\s+([0-9\-.]+)\s+\)$', line)
            if result:
                forces.append([result.group(1), result.group(2), result.group(3)])

            # End of task
            if re.match('^ Task  times  cpu:', line):
                result = re.match(r'^ Task  times  cpu:\s*([\d\.\d]+)s\s*wall:\s*([\d\.\d]+)s', line)
                result_dict['cpu_time'] = result.group(1)
                result_dict['wall_time'] = result.group(2)
                break

        if forces:
            result_dict['forces'] = forces

        return result_dict


    def parse_tce(self,lines):
        """
        Parse a TCE task block

        args: lines: the lines to parse
        """

        result_dict = {'theory': 'tce'}
        state = None

        for line in lines:

            result = re.match(r'^[\s]+Wavefunction type :([A-z\s-]+)\s*$',line)
            if result:
                result_dict['wavefunction_type'] = result.group(1).strip()

            result = re.match(r'^\s+Spin multiplicity :\s*([A-z]+)\s*$',line)
            if result:
                result_dict['spin_multiplicity'] = result.group(1)

            result = re.match(r'^\s+Number of AO functions :\s*([0-9]+)$',line)
            if result:
                result_dict['number_of_AO_functions'] = result.group(1)

            result = re.match(r'^[\s]+Calculation type :([A-z\s,&-]+)\s*$',line)
            if result:
                result_dict['calculation_type'] = result.group(1).strip()

            if re.match(r'^\s*Iterations converged\s*$',line):
                state = 'final-results'
            if state == 'final-results':
                result = re.match(r'^\s*([^=]+?)\s*=\s*([\-\d\.]+)$',line)
                if result:
                    key = re.sub(r'[^a-zA-Z0-9]+', '_', result.group(1).lower())
                    result_dict[key] = result.group(2)

            # End of task
            if re.match('^ Task  times  cpu:', line):
                result = re.match(r'^ Task  times  cpu:\s*([\d\.\d]+)s\s*wall:\s*([\d\.\d]+)s', line)
                result_dict['cpu_time'] = result.group(1)
                result_dict['wall_time'] = result.group(2)
                break

        return result_dict


    def parse_energy(self, task_lines, theory_type, create_node=True):
        """
        Parse an energy task block

        param: lines: the lines to parse
        """
        module_parser = getattr(self, 'parse_'+theory_type)
        result_dict = module_parser(task_lines)
        if create_node:
            self.out('output_parameters', orm.Dict(dict=result_dict))
        else:
            return result_dict

    def parse_geoopt(self, task_lines, theory_type):
        """
        Parse a geometry optimisation task block

        params: lines: the lines to parse
        """

        result_dict = {'task':'geo-opt'}
        state = None
        symbols = []
        positions = []
        cell = []

        for line in task_lines:
            if re.match(r'^\s*Optimization converged\s*$',line):
                state = 'final-results'
                continue
            if state == 'final-results':
                # Parse step and energy
                result = re.match(r'^@\s*([\d]+)\s*([\-\d\.]+)',line)
                if result:
                    result_dict['final_step'] = result.group(1)
                    result_dict['final_opt_energy'] = result.group(2)
                    continue
                # Parse coords
                if re.match(r'^\s*Output coordinates in angstroms',line):
                    state = 'final-coords'
                    continue
                # Parse cell
                if re.match(r'^\s*lattice vectors in angstroms',line):
                    state = 'final-cell'
                    continue
            if state == 'final-coords':
                result = re.match(r'^\s*[\d]+\s*([a-zA-Z]+)\s*[\-\d\.]+'
                                  r'\s*([\-\d\.]+)\s*([\-\d\.]+)\s*([\-\d\.]+)$', line)
                if result:
                    symbols.append(result.group(1))
                    positions.append([result.group(2),result.group(3),result.group(4)])
                    continue
                else:
                    if re.match(r'^\s*lattice vectors in angstroms',line):
                        state = 'final-cell'
                        continue
                    if re.match(r'^$|^[\sA-z\.-]+$', line):
                        continue
                    else:
                        state = 'final-results'
                        continue
            if state == 'final-cell':
                if re.match(r'^\s*reciprocal lattice vectors',line):
                    state = 'final-results'
                    continue
                else:
                    result = re.match(r'^\s*a[1-3]=<\s*([\d\.\d]+)\s*([\d\.\d]+)\s*([\d\.\d]+)', line)
                    if result:
                        cell.append([result.group(1),result.group(2),result.group(3)])
                        continue
                    else:
                        continue

            if re.match(r'^ Task  times  cpu:', line):
                result = re.match(r'^ Task  times  cpu:\s*([\d\.\d]+)s\s*wall:\s*([\d\.\d]+)s', line)
                result_dict['cpu_time'] = result.group(1)
                result_dict['wall_time'] = result.group(2)
                break

        for index, line in enumerate(task_lines):
            if re.match(r'^@\s+([0-9]+).*$', line):
                result = re.match(r'^@\s+([0-9]+).*$', line)
                step_number = int(result.group(1))
                if step_number == int(result_dict['final_step']):
                    last_line = index
                    continue
            elif re.match(r'^\s+Step\s+([0-9]+)\s*$', line):
                result = re.match(r'^\s+Step\s+([0-9]+)\s*$', line)
                step_number = int(result.group(1))
                if step_number == int(result_dict['final_step']):
                    first_line = index
                    continue
        final_energy_lines = task_lines[first_line:last_line]
        final_energy_dict = self.parse_energy(final_energy_lines, theory_type, create_node=False)

        result_dict['final_energy'] = final_energy_dict

        self.out('output_parameters', orm.Dict(dict=result_dict))

        # Create StructureData node
        if positions:
            positions = np.array(positions, np.float64)

        if not cell:
            # If the cell is specified, ASE defaults to 0,0,0, which throws an AiiDA
            # error for cell with volume of 0. Here we arbitrarily set the cell.
            # This isn't really satisfactory.
            # TODO: Look into changing AiiDA test of cell volume.
            cell = (1.,1.,1.)
        else:
            cell = np.array(cell, np.float64)
        self.out('output_structure', orm.StructureData(ase=Atoms(symbols=symbols, positions=positions, cell=cell)))

        return

    def parse_freq(self, task_lines, theory_type):
        """
        Parse a frequency analysis task block

        param: lines: the lines to parse
        returns: task_dict: a dictionary of results for the task
        nodes: the nodes created by parsing
        """

        task_dict = {'task':'freq'}
        nodes = []
        state = None

        for line in task_lines:

            if re.match(r'^\s*Rotational Constants\s*$',line):
                state = 'final-results'
                continue
            if state == 'final-results':
                result = re.match(r'^\s([A-z\s\(\)\-]+)\s+=\s*([\d\.]+)',line)
                if result:
                    if result.group(1).strip() == 'Total Entropy':
                        state = 'final-entropy'
                        task_dict['entropy'] = {}
                        key = re.sub('[^a-zA-Z0-9]+', '_', result.group(1).strip().lower())
                        task_dict['entropy'][key] = result.group(2)
                        continue
                    elif result.group(1) == 'Cv (constant volume heat capacity)':
                        state = 'final-cv'
                        task_dict['heat_capacity'] = {}
                        task_dict['heat_capacity']['total'] = result.group(2)
                        continue
                    else:
                        key = re.sub('[^a-zA-Z0-9]+', '_', result.group(1).strip().lower())
                        task_dict[key] = result.group(2)
                        continue
                # Derivative Dipole
                if re.search('Projected Derivative Dipole',line):
                    state = 'final-freq-results-dipole'
                    dipoles_list = []
                    frequencies = []
                    continue
                # Infrared
                if re.search('Projected Infra Red',line):
                    state = 'final-freq-results-ir'
                    intensities = []
                    continue
            # Entropy
            if state == 'final-entropy':
                result = re.match(r'^\s*-\s([A-z\s\(\)]+)\s+=\s*([\d\.]+)',line)
                if result:
                    key = re.sub(r'[^a-zA-Z0-9]+', '_', result.group(1).strip().lower())
                    task_dict['entropy'][key] = result.group(2)
                else:
                    state = 'final-results'
                    continue
            # Heat capacity
            if state == 'final-cv':
                result = re.match(r'^\s*-\s([A-z\s\(\)]+)\s*=\s*([\d\.]+)',line)
                if result:
                    key = re.sub('[^a-zA-Z0-9]+', '_', result.group(1).strip().lower())
                    task_dict['heat_capacity'][key] = result.group(2)
                else:
                    state = 'final-results'
                    continue
            # Parse dipole data
            if state == 'final-freq-results-dipole':
                result = re.match(r'^\s*[\d]\s*([\-\d\.]+)\s*\|\|'
                                  r'\s*([-\d.]+)\s*([-\d.]+)\s*([-\d.]+)$',line)
                if result:
                    # Get vibrational eigenvalues (cm^-1)
                    frequencies.append(result.group(1))
                    # Get dipole moments (cartesian, debye/angs)
                    dipoles_list.append([result.group(2), result.group(3), result.group(4)])
                    continue
                if re.match('^\s-+$', line):
                    state = 'final-results'
                    task_dict['frequencies'] = frequencies
                    task_dict['dipoles'] = np.array(dipoles_list, np.float64)
                    continue
            # Parse IR data
            if state == 'final-freq-results-ir':
                result = re.match(r'^\s*[\d]\s*[\-\d\.]+\s*\|\|\s*([-\d.]+)'
                                  r'\s*([-\d.]+)\s*([-\d.]+)\s*([-\d.]+)$',line)
                if result:
                    # Get intensity (arbitrary units)
                    intensities.append(result.group(4))
                    continue
                if re.match('^\s-+$', line):
                    state = 'final-results'
                    task_dict['ir-intensities'] = intensities
                    continue
            # End of task
            if re.match('^ Task  times  cpu:', line):
                result = re.match(r'^ Task  times  cpu:\s*([\d\.\d]+)s'
                                  r'\s*wall:\s*([\d\.\d]+)s', line)
                task_dict['cpu_time'] = result.group(1)
                task_dict['wall_time'] = result.group(2)
                break

        return task_dict, nodes














