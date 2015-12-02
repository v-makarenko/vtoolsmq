"""
qtools.components was an experiment in designing
components around the Dependency Injection pattern.

In this pattern, the actual code that will take
the role of an actor is often specified at runtime,
or config time, rather than using a tight coupling
between components hardcoded into the source code.

Here, services using DI components rely on a manager
(qtools.components.manager) to return the service
that will perform the desired task.  The manager,
when constructed, uses the values stored in the
config file to construct services.  The names of
the modules corresponding to certain services are
in the config file, and can theoretically be
changed if an alternate service is needed (I never
went this far.)

The main service in QTools that uses dependency
injection and the manager is a JobQueue, which is
a component responsible for detecting new
background jobs and running them.  I anticipated
that we may have a customer-facing assay design
website.  This job queue could have a variety of
forms, which may be different in production than
in development.

In retrospect, this is a little overkill for a
one-man show, but could be good in a mock testing
environment.
"""