from odoo import models, api
import time
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class OrderSummaryBenchmark(models.Model):
    _name = 'order.summary.benchmark'
    _description = 'Order Summary Performance Benchmark'

    def run_benchmark(self, dataset_sizes=[1000, 10000, 50000]):
        """Run performance benchmarks for different dataset sizes"""
        results = {}

        for size in dataset_sizes:
            _logger.info(f"Running benchmark for {size} records...")

            query_time = self._benchmark_query()

            results[size] = {
                'query_time_ms': query_time * 1000,
                'timestamp': datetime.now().isoformat()
            }

        return results

    def _benchmark_query(self):
        """Benchmark the optimized query"""
        order_summary = self.env['order.summary']

        start_time = time.time()
        for _ in range(5):
            order_summary.get_order_summary_data()
        end_time = time.time()

        return (end_time - start_time) / 5