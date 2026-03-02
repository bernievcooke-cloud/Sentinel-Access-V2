# report_wrapper.py

class ReportWrapper:
    def __init__(self):
        # Initialize report wrapper
        pass

    def route_to_worker(self, report_type):
        """Routes the report to the correct worker based on report type."""
        if report_type == 'type_a':
            return self.worker_type_a()
        elif report_type == 'type_b':
            return self.worker_type_b()
        else:
            raise ValueError('Unknown report type')

    def worker_type_a(self):
        # Implementation for worker type A
        return 'Processing with worker A'

    def worker_type_b(self):
        # Implementation for worker type B
        return 'Processing with worker B'