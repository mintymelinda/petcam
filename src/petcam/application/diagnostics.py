"""Application-level diagnostics and support-bundle use cases."""


def collect(collector):
    return collector()


def create_support_bundle(builder, performance=None):
    return builder(performance=performance)
