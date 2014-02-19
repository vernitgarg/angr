#!/usr/bin/env python

import simuvex
from angr import Surveyor

import collections
import logging
l = logging.getLogger("angr.surveyors.Explorer")

class Explorer(Surveyor):
	'''
	Explorer implements a symbolic exploration engine!

		found - paths where the target addresses have been found
		avoided - paths where the to-avoid addresses have been found
		deviating - paths that deviate from the restricted-to addresses
		looping - paths that were detected as looping
	'''

	def __init__(self, project, start=None, starts=None, max_concurrency=None, mode=None, options=None, find=(), avoid=(), restrict=(), min_depth=0, max_depth=100  , max_repeats=10):
		'''
		Explores the path space until a block containing a specified address is
		found. Parameters:

		@param project: the angr.Project to analyze
		@param start: a single exit to start the analysis on
		@param starts: the exits to start the analysis on. If neither this nor start are given,
					   the analysis starts from p.initial_exit()
		@param max_concurrency: the maximum number of paths to explore at a time

		@param find: a tuple containing the addresses to search for
		@param avoid: a tuple containing the addresses to avoid
		@param restrict: a tuple containing the addresses to restrict the
						 analysis to (i.e., avoid all others)
		@param min_depth: the minimum number of SimRuns in the resulting
		path
		@param max_depth: the maximum number of SimRuns in the resulting
		path
		'''
		Surveyor.__init__(self, project, start=start, starts=starts, max_concurrency=max_concurrency, mode=mode, options=options)

		# initialize the counter
		self._instruction_counter = collections.Counter()

		self._find = set(find)
		self._avoid = set(avoid)
		self._restrict = set(restrict)
		self._max_repeats = max_repeats
		self._max_depth = max_depth
		self._min_depth = min_depth
		self._current_depth = 0

		self.found = [ ]
		self.avoided = [ ]
		self.deviating = [ ]
		self.looping = [ ]

	def path_comparator(self, x, y):
		return self._instruction_counter[x.last_run.addr] - self._instruction_counter[y.last_run.addr]

	@property
	def done(self):
		if self._current_depth < self._min_depth:
			return False

		if len(self.active) == 0:
			l.debug("Done because we have no active paths left!")
			return True

		if len(self.found) > 0:
			l.debug("Done because we found the targets on %d path(s)!", len(self.found))
			return True

		return False

	def tick(self):
		'''
		Takes one step in the analysis. Typically, this moves all active paths
		forward.
		'''
		l.debug("At depth %d out of %d, with %d paths.", self._current_depth, self._max_depth, len(self.active))

		Surveyor.tick(self)
		self._current_depth += 1

		# just do this for now if we're below the limit
		if self._current_depth < self._min_depth:
			return self

		# now split the paths out
		still_active = []
		for p in self.active:
			if isinstance(p.last_run, simuvex.SimIRSB):
				imark_set = set(p.last_run.imark_addrs())
			else:
				imark_set = { p.last_run.addr }

			for addr in imark_set:
				self._instruction_counter[addr] += 1

			find_intersection = imark_set & self._find
			avoid_intersection = imark_set & self._avoid
			restrict_intersection = imark_set & self._restrict

			if len(avoid_intersection) > 0:
				l.debug("Avoiding path %s due to matched avoid addresses: %s", p, avoid_intersection)
				self.avoided.append(p)
			elif len(find_intersection) > 0:
				l.debug("Marking path %s as found due to matched target addresses: %s", p, [ "0x%x" % _ for _ in find_intersection ])
				self.found.append(p)
			elif len(self._restrict) > 0 and len(restrict_intersection) == 0:
				l.debug("Path %s is not on the restricted addresses!", p)
				self.deviating.append(p)
			elif collections.Counter(p.backtrace).most_common(1)[0][1] > self._max_repeats:
				# discard any paths that loop too much
				l.debug("Path %s appears to be looping!", p)
				self.looping.append(p)
			else:
				still_active.append(p)

			self.active = still_active

	def trim(self):
		# if there are too many paths, prioritize the ones that are
		# executing less-commonly-seen instructions
		if len(self.active) > self._max_concurrency:
			# first, filter them down to only the satisfiable ones
			l.debug("Trimming %d paths to avoid a state explosion.", len(self.active) - self._max_concurrency)
			self.active.sort(cmp=self.path_comparator)
			self.trimmed += self.active[self._max_concurrency:]
			self.active = self.active[:self._max_concurrency]

	def report(self):
		return "%d found, %d avoided, %d deviating, %d looping" % (len(self.found), len(self.avoided), len(self.deviating), len(self.looping))
