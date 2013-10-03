#!/usr/bin/env python
import z3
import s_value
import random
import copy
import collections
import logging

logging.basicConfig()
l = logging.getLogger("s_memory")
addr_mem_counter = 0
var_mem_counter = 0

l.setLevel(logging.DEBUG)

class Memory:
    def __init__(self, initial=None, sys=None, id="mem"):
        def default_mem_value():
            global var_mem_counter
            var = z3.BitVec("%s_%d" % (id, var_mem_counter), 8)
            var_mem_counter += 1
            return var

        #TODO: copy-on-write behaviour
        self.__mem = copy.copy(initial) if initial else collections.defaultdict(default_mem_value)
        self.__limit = 1024
        self.__bits = sys if sys else 64
        self.__max_mem = 2**self.__bits
        self.__freemem = [(0, self.__max_mem - 1)]


    def store(self, dst, cnt, constraints):
        if len(self.__mem) + cnt.size() >= self.__max_mem:
            raise Exception("Memory is full.")

        v = s_value.Value(dst, constraints)
        ret = []

        if v.is_unique():
            addr = v.any()
        else:
            s = z3.Solver()
            con = False
            for i in range(0, len(self.__freemem)):
                con = z3.Or(z3.And(z3.UGE(dst, self.__freemem[i][0]), z3.ULE(dst, self.__freemem[i][1])), con)
            con = z3.simplify(con)

            if con == True: # if it is always satisfiable%
                addr = random.randint(0, self.__max_mem)
                ret = [dst == addr]
            else:
                s.add(con)
                if s.check() == z3.unsat:
                    raise Exception("Unable to store new values in memory.")
                addr = s.model().get_interp(dst)
                ret = [dst == addr]

        for off in range(0, cnt.size() / 8):
            self.__mem[(addr + off)] = z3.Extract((off << 3) + 7, (off << 3), cnt)

        keys = [ -1 ] + self.__mem.keys() + [ self.__max_mem ]
        self.__freemem = [ j for j in [ ((keys[i] + 1, keys[i+1] - 1) if keys[i+1] - keys[i] > 1 else ()) for i in range(len(keys)-1) ] if j ]

        return ret

    #Load expressions from memory
    def load(self, dst, size, constraints=None):
        global addr_mem_counter

        if len(self.__mem) == 0:
            return self.__mem[-1], []

        expr = False
        ret = None

        size_b = size >> 3
        v = s_value.Value(dst, constraints)

        # specific read
        if v.is_unique():
            addr = v.any()
            expr = self.__mem[addr] if (size_b == 1) else z3.Concat(*[self.__mem[addr + i] for i in range( 0, size_b)])
            expr = z3.simplify(expr)
            ret = expr, []

        elif abs(v.max() - v.min()) <= self.__limit:
            w_k = range(v.min(), v.max())
            w_k.append(v.max())
            p_k = list(set(w_k) & set(self.__mem.keys()))

            if len(p_k) == 0:
                l.debug("Loading operation outside its boundaries, symbolic variable found")
                expr = self.__mem[-1]
            else:
                var = z3.BitVec("%s_addr_%s" %(dst, addr_mem_counter), self.__bits)
                addr_mem_counter += 1
                for addr in p_k:
                    cnc = z3.Concat(*[self.__mem[addr + i] for i in range( 0, size_b)])
                    expr = z3.simplify(z3.Or(var == cnc, expr))
                ret = expr, []
        else:
            addr = random.choice(self.__mem.keys())
            cnc = z3.Concat(*[ self.__mem[addr + i] for i in range( 0, size_b)])
            cnc = z3.simplify(cnc)
            ret = cnc, [dst == addr]

        return ret

    def get_bit_address(self):
        return self.__bits

    #TODO: copy-on-write behaviour
    def copy(self):
        return copy.copy(self)
