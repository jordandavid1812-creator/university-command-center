"""Keep PostgreSQL from rounding credits before CHECK constraints run."""
from django.db import models


class ExactCreditField(models.DecimalField):
    def db_type(self, connection):
        # numeric(p,s) silently rounds excess fractional digits. Unconstrained
        # numeric plus explicit range/scale checks rejects them instead.
        if connection.vendor != "postgresql":
            raise NotImplementedError("The foundation requires PostgreSQL.")
        return "numeric"
