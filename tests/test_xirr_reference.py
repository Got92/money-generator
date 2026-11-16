"""Independent annual-cash-flow oracle: polynomial roots, not JS root isolation."""
import datetime as dt
import json
from pathlib import Path
import random
import subprocess
import unittest

import numpy as np


class XirrReferenceTest(unittest.TestCase):
    def test_two_hundred_deterministic_ledgers_match_polynomial_roots(self):
        rng = random.Random(42)
        cases = []
        for _ in range(200):
            coefficients = [rng.randint(-1000, 1000) or 1 for _ in range(rng.randint(2, 8))]
            flows = [{'date': (dt.date(2010, 1, 1)+dt.timedelta(days=365*i)).isoformat(), 'amount': value}
                     for i, value in enumerate(coefficients)]
            # With exact 365-day intervals, y=1+r turns NPV into this polynomial.
            roots = [r.real-1 for r in np.roots(coefficients) if abs(r.imag) < 1e-7 and r.real > 0]
            cases.append({'flows': flows, 'roots': roots})
        script = """import {xirr} from './src/xirr.js';
let input='';for await(const chunk of process.stdin)input+=chunk;
process.stdout.write(JSON.stringify(JSON.parse(input).map(c=>xirr(c.flows))));"""
        process = subprocess.run(['node', '--input-type=module', '-e', script],
                                 cwd=Path(__file__).resolve().parents[1], input=json.dumps(cases),
                                 text=True, capture_output=True, check=True, timeout=30)
        for case, actual in zip(cases, json.loads(process.stdout)):
            with self.subTest(flows=case['flows']):
                expected = case['roots']
                if len(expected) == 1:
                    self.assertIsNotNone(actual)
                    self.assertAlmostEqual(actual, expected[0], delta=1e-7*max(1, abs(expected[0])))
                else:
                    self.assertIsNone(actual)
