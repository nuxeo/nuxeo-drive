
# Understanding database Session and Transaction management with SQLAlchemy

For full documentation see:

[Using the Session](http://docs.sqlalchemy.org/en/latest/orm/session.html)

[Working with Engines and Connections](http://docs.sqlalchemy.org/en/latest/core/connections.html)

## Session lifecycle

As a general rule, an application should manage the lifecycle of the session externally to functions that deal with specific data.
This is a fundamental separation of concerns which keeps data-specific operations agnostic of the context in which they access and manipulate that data.

**E.g. don’t do this:**

    ### this is the **wrong way to do it** ###

    class ThingOne(object):
        def go(self):
            session = Session()
            try:
                session.query(FooBar).update({"x": 5})
                session.commit()
            except:
                session.rollback()
                raise

    class ThingTwo(object):
        def go(self):
            session = Session()
            try:
                session.query(Widget).update({"q": 18})
                session.commit()
            except:
                session.rollback()
                raise

    def run_my_program():
        ThingOne().go()
        ThingTwo().go()

**Keep the lifecycle of the session (and usually the transaction) separate and external:**

    ### this is a **better** (but not the only) way to do it ###

    class ThingOne(object):
        def go(self, session):
            session.query(FooBar).update({"x": 5})

    class ThingTwo(object):
        def go(self, session):
            session.query(Widget).update({"q": 18})

    def run_my_program():
        session = Session()
        try:
            ThingOne().go(session)
            ThingTwo().go(session)

            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

## Session thread-safety

The Session is very much intended to be used in a non-concurrent fashion, which usually means in only one thread at a time.

Making sure the Session is only used in a single concurrent thread at a time is called a “share nothing” approach to concurrency.
But actually, not sharing the Session implies a more significant pattern; it means not just the Session object itself,
but also all objects that are associated with that Session, must be kept within the scope of a single concurrent thread.
The set of mapped objects associated with a Session are essentially proxies for data within database rows accessed over a database connection,
and so just like the Session itself, the whole set of objects is really just a large-scale proxy for a database connection (or connections).
Ultimately, it’s mostly the DBAPI connection itself that we’re keeping away from concurrent access;
but since the Session and all the objects associated with it are all proxies for that DBAPI connection, the entire graph is essentially not safe for concurrent access.

One expedient way to get this effect is by associating a Session with the current thread using the Thread-local scope
guaranteed by the `scoped_session` object.

In Nuxeo Drive we use this scope by passing `scoped_sessions=True` in `nxdrive.model.init_db()`.

## Default transaction management and Session states

First note that Session, Connection, Transaction, Engine are SQLAlchemy objects.

- A newly constructed Session is in the "begin" state => no connection to the database is opened yet and no transaction started.
- When calling `Session.query()`, `Session.execute()`, `Session.commit()` or `Session.flush()` the Session enters a "transactional" state.
- A Connection to the database is acquired through the Engine bound to the Session.
- A Transaction begins through this Connection.
- The Transaction is only commited or rollbacked by explicit calls to `Session.commit()` or `Session.rollback()`.
- The Session goes back to the "begin" state.

Thus the right pattern to follow is:

    engine = create_engine("...")
    Session = sessionmaker(bind=engine)

    # new session.   no connections are in use.
    session = Session()
    try:
        # first query.  a Connection is acquired
        # from the Engine, and a Transaction
        # started.
        item1 = session.query(Item).get(1)

        # second query.  the same Connection/Transaction
        # are used.
        item2 = session.query(Item).get(2)

        # pending changes are created.
        item1.foo = 'bar'
        item2.bar = 'foo'

        # commit.  The pending changes above
        # are flushed via flush(), the Transaction
        # is committed, the Connection object closed
        # and discarded, the underlying DBAPI connection
        # returned to the connection pool.
        session.commit()
    except:
        # on rollback, the same closure of state
        # as that of commit proceeds.
        session.rollback()
        raise

Note that nested transactions are also possible.

## Autocommit mode

By default not activated. Can be activated when making a Session:

    Session = sessionmaker(bind=engine, autocommit=True)

"autocommit" mode should not be considered for general use.
If used, it should always be combined with the usage of `Session.begin()` and `Session.commit()`, to ensure a transaction demarcation.
Modern usage of `autocommit` is for framework integrations that need to control specifically when the "begin" state occurs.

In which case this pattern can be applied:

    Session = sessionmaker(bind=engine, autocommit=True)
    session = Session()
    session.begin()
    try:
        item1 = session.query(Item).get(1)
        item2 = session.query(Item).get(2)
        item1.foo = 'bar'
        item2.bar = 'foo'
        session.commit()
    except:
        session.rollback()
        raise

