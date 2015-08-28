# This file is part of the Go-Smart Simulation Architecture (GSSA).
# Go-Smart is an EU-FP7 project, funded by the European Commission.
#
# Copyright (C) 2013-  NUMA Engineering Ltd. (see AUTHORS file)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from autobahn.asyncio.wamp import ApplicationSession
import uuid
from lxml import etree as ET
import asyncio
import os
import tarfile
import tempfile


# This should be adjusted when this issue resolution hits PIP: https://github.com/tavendo/AutobahnPython/issues/332
# http://stackoverflow.com/questions/28293198/calling-a-remote-procedure-from-a-subscriber-and-resolving-the-asyncio-promise
from functools import wraps
def wrapped_coroutine(f):
    def wrapper(*args, **kwargs):
        coro = f(*args, **kwargs)
        asyncio.async(coro)
    return wrapper
#endSO


class GoSmartSimulationClientComponent(ApplicationSession):

    def __init__(self, x, gssa_file, subdirectory, output_files, input_files=None, definition_files=None, skip_clean=False):
        ApplicationSession.__init__(self, x)
        self._gssa = ET.parse(gssa_file)
        self._definition_files = definition_files
        self._input_files = input_files

        if self._definition_files is not None:
            self._definition_tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz')
            definition_tar = tarfile.open(fileobj=self._definition_tmp, mode='w:gz')
            for definition_file in self._definition_files:
                definition_tar.add(definition_file, os.path.basename(definition_file))
                print("Added [%s]" % os.path.basename(definition_file))
            definition_tar.close()
            self._definition_tmp.flush()
            print("Made temporary tar at %s" % self._definition_tmp.name)
            definition_node = self._gssa.find('.//definition')
            definition_node.set('location', self._definition_tmp.name)

        if self._input_files is not None:
            self._input_tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz')
            input_tar = tarfile.open(fileobj=self._input_tmp, mode='w:gz')
            for input_file in self._input_files:
                input_tar.add(input_file, os.path.basename(input_file))
                print("Added [%s]" % os.path.basename(input_file))
            input_tar.close()
            self._input_tmp.flush()
            print("Made temporary tar at %s" % self._input_tmp.name)
            input_node = ET.SubElement(self._gssa.find('.//transferrer'), 'input')
            input_node.set('location', self._input_tmp.name)

        self._guid = uuid.uuid1()
        self._subdirectory = subdirectory
        self._output_files = output_files
        self._skip_clean = skip_clean

    @asyncio.coroutine
    def onJoin(self, details):
        print("session ready")

        guid = str(self._guid)
        gssa = ET.tostring(self._gssa, encoding="unicode")
        yield from self.call('com.gosmartsimulation.init', guid)
        print("Initiated...")
        yield from self.call('com.gosmartsimulation.update_settings_xml', guid, gssa)
        print("Sent XML...")
        yield from self.call('com.gosmartsimulation.finalize', guid, self._subdirectory)
        print("Finalized settings...")
        yield from self.call('com.gosmartsimulation.start', guid)
        print("Started...")
        self.subscribe(self.onComplete, 'com.gosmartsimulation.complete')
        self.subscribe(self.onFail, 'com.gosmartsimulation.fail')

    @wrapped_coroutine
    @asyncio.coroutine
    def onComplete(self, guid, success, time, validation):
        print("Complete")
        if validation:
            print("Validation:", validation)
        print("Requesting files")
        files = yield from self.call('com.gosmartsimulation.request_files', guid, {
            f: os.path.join('/tmp', f) for f in self._output_files
        })
        print(files)
        yield from self.finalize(guid)

    @wrapped_coroutine
    @asyncio.coroutine
    def onFail(self, guid, message, time):
        print("Failed - %s" % message)
        yield from self.finalize(guid)

    def finalize(self, guid):
        if not self._skip_clean:
            yield from self.call('com.gosmartsimulation.clean', guid)
            self.shutdown()
        else:
            print("Skipping clean-up")

    def shutdown(self):
        self.leave()

    def onLeave(self):
        self.disconnect()
