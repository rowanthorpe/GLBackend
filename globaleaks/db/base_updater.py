# -*- encoding: utf-8 -*-
import os

from storm.exceptions import OperationalError
from storm.locals import *
from storm.properties import PropertyColumn
from storm.variables import BoolVariable, DateTimeVariable
from storm.variables import EnumVariable, IntVariable, RawStrVariable
from storm.variables import UnicodeVariable, JSONVariable, PickleVariable

from globaleaks import models
from globaleaks.settings import GLSetting
from globaleaks import DATABASE_VERSION

# This code is take directly from the GlobaLeaks-pre-model-refactor

def variableToSQLite(var_type):
    """
    We take as input a storm.variable and we output the SQLite string it
    represents.
    """
    sqlite_type = "VARCHAR"
    if isinstance(var_type, BoolVariable):
        sqlite_type = "INTEGER"
    elif isinstance(var_type, DateTimeVariable):
        pass
    elif isinstance(var_type, EnumVariable):
        sqlite_type = "BLOB"
    elif isinstance(var_type, IntVariable):
        sqlite_type = "INTEGER"
    elif isinstance(var_type, RawStrVariable):
        sqlite_type = "BLOB"
    elif isinstance(var_type, UnicodeVariable):
        pass
    elif isinstance(var_type, JSONVariable):
        sqlite_type = "BLOB"
    elif isinstance(var_type, PickleVariable):
        sqlite_type = "BLOB"
    else:
        raise AssertionError("Invalid var_type: %s" % var_type)

    return "%s" % sqlite_type

def varsToParametersSQLite(variables, primary_keys):
    """
    Takes as input a list of variables (convered to SQLite syntax and in the
    form of strings) and primary_keys.
    Outputs these variables converted into paramter syntax for SQLites.

    ex.
        variables: ["var1 INTEGER", "var2 BOOL", "var3 INTEGER"]
        primary_keys: ["var1"]

        output: "(var1 INTEGER, var2 BOOL, var3 INTEGER PRIMARY KEY (var1))"
    """
    params = "("
    for var in variables[:-1]:
        params += "%s %s, " % (var[0], var[1])
    if len(primary_keys) > 0:
        params += "%s %s, " % variables[-1]
        params += "PRIMARY KEY ("
        for key in primary_keys[:-1]:
            params += "%s, " % key
        params += "%s))" % primary_keys[-1]
    else:
        params += "%s %s)" % variables[-1]
    return params

def generateCreateQuery(model):
    """
    This takes as input a Storm model and outputs the creation query for it.
    """
    prehistory = model.__storm_table__.find("_version_")
    if prehistory != -1:
        table_name = model.__storm_table__[:prehistory]
    else:
        table_name = model.__storm_table__

    query = "CREATE TABLE "+ table_name + " "

    variables = []
    primary_keys = []

    for attr in dir(model):
        a = getattr(model, attr)
        if isinstance(a, PropertyColumn):
            var_stype = a.variable_factory()
            var_type = variableToSQLite(var_stype)
            name = a.name
            variables.append((name, var_type))
            if a.primary:
                primary_keys.append(name)

    query += varsToParametersSQLite(variables, primary_keys)
    return query


class TableReplacer:
    """
    This is the base class used by every Updater
    """

    def __init__(self, old_db_file, new_db_file, start_ver):

        from globaleaks.db.update_5_6 import User_version_5, Comment_version_5, Node_version_5
        from globaleaks.db.update_6_7 import Node_version_6, Context_version_6

        self.old_db_file = old_db_file
        self.new_db_file = new_db_file
        self.start_ver = start_ver

        self.std_fancy = " ł "
        self.debug_info = "   [%d => %d] " % (start_ver, start_ver + 1)

        self.table_history = {
            'Node' : [ Node_version_5, Node_version_6, models.Node ],
            'User' : [ User_version_5, models.User, None ],
            'Context' : [ Context_version_6, None, models.Context ],
            'Receiver': [ models.Receiver, None, None ],
            'ReceiverFile' : [ models.ReceiverFile, None, None ],
            'Notification': [ models.Notification, None, None ],
            'Comment': [ Comment_version_5, models.Comment, None ],
            'InternalTip' : [ models.InternalTip, None, None ],
            'InternalFile' : [ models.InternalFile, None, None ],
            'WhistleblowerTip' : [ models.WhistleblowerTip, None, None ],
            'ReceiverTip' : [ models.ReceiverTip, None, None ],
            'ReceiverInternalTip' : [ models.ReceiverInternalTip, None, None ],
            'ReceiverContext' : [ models.ReceiverContext, None, None ],
        }

        for k, v in self.table_history.iteritems():
            # +1 because count start from 0,
            # -5 because the relase 0,1,2,3,4 are not supported anymore
            assert len(v) == (DATABASE_VERSION + 1 - 5), \
                "I'm expecting a table with %d statuses (%s)" % (DATABASE_VERSION, k)

        print "%s Opening old DB: %s" % (self.debug_info, old_db_file)
        old_database = create_database("sqlite:%s" % self.old_db_file)
        self.store_old = Store(old_database)

        GLSetting.db_file = new_db_file

        new_database = create_database("sqlite:%s" % new_db_file)
        self.store_new = Store(new_database)

        if self.start_ver + 1 == DATABASE_VERSION:

            print "%s Acquire SQL schema %s" % (self.debug_info, GLSetting.db_schema_file)

            if not os.access(GLSetting.db_schema_file, os.R_OK):
                print "Unable to access %s" % GLSetting.db_schema_file
                raise Exception("Unable to access db schema file")

            with open(GLSetting.db_schema_file) as f:
                create_queries = ''.join(f.readlines()).split(';')
                for create_query in create_queries:
                    try:
                        self.store_new.execute(create_query+';')
                    except OperationalError:
                        print "OperationalError in [%s]" % create_query

            self.store_new.commit()
            return
            # return here and manage the migrant versions here:

        for k, v in self.table_history.iteritems():

            create_query = self.get_right_sql_version(k, self.start_ver +1)
            if not create_query:
                # table not present in the version
                continue

            try:
                self.store_new.execute(create_query+';')
            except OperationalError as excep:
                print "%s OperationalError in [%s]" % (self.debug_info, create_query)
                raise excep

        self.store_new.commit()

    def close(self):
        self.store_old.close()
        self.store_new.close()

    def initialize(self):
        pass

    def epilogue(self):
        pass

    def get_right_model(self, table_name, version):

        table_index = (version - 5)

        if not self.table_history.has_key(table_name):
            print "Not implemented usage of get_right_model %s (%s %d)" % (
                __file__, table_name, self.start_ver)
            raise NotImplementedError

        assert version <= DATABASE_VERSION, "wrong developer brainsync"

        if self.table_history[table_name][table_index]:
            # print "Immediate return %s = %s at version %d" % \
            #       ( table_name, self.table_history[table_name][table_index], version )
            return self.table_history[table_name][table_index]

        # else, it's none, and we've to take the previous valid version
        #
        # print "Requested version %d of %s need to be collected in the past" %\
        #       (version, table_name)

        while version >= 0:
            if self.table_history[table_name][table_index]:
            # print ".. returning %s = %s" %\
            #           ( table_name, self.table_history[table_name][table_index] )
                return self.table_history[table_name][table_index]
            table_index -= 1

        # This never want happen
        return None

    def get_right_sql_version(self, model_name, version):
        """
        @param model_name:
        @param version:
        @return:
            The SQL right for the stuff we've
        """

        modelobj = self.get_right_model(model_name, version)
        if not modelobj:
            return None

        right_query = generateCreateQuery(modelobj)
        return right_query

    def _perform_copy_list(self, table_name):

        print "%s default %s migration assistant: #%d" % (
            self.debug_info, table_name,
            self.store_old.find(self.get_right_model(table_name, self.start_ver)).count())

        old_objects = self.store_old.find(self.get_right_model(table_name, self.start_ver))

        for old_obj in old_objects:
            new_obj = self.get_right_model(table_name, self.start_ver + 1)()

            # Storm internals simply reversed
            for k, v in new_obj._storm_columns.iteritems():
                setattr(new_obj, v.name, getattr(old_obj, v.name) )

            self.store_new.add(new_obj)
        self.store_new.commit()

    def _perform_copy_single(self, table_name):
        print "%s default %s migration assistant" % (self.debug_info, table_name)

        old_obj = self.store_old.find(self.get_right_model(table_name, self.start_ver)).one()
        new_obj = self.get_right_model(table_name, self.start_ver + 1)()

        # Storm internals simply reversed
        for k, v in new_obj._storm_columns.iteritems():
            setattr(new_obj, v.name, getattr(old_obj, v.name) )

        self.store_new.add(new_obj)
        self.store_new.commit()

    def migrate_Context(self):
        self._perform_copy_list("Context")

    def migrate_Node(self):
        self._perform_copy_single("Node")

    def migrate_User(self):
        """
        It's created between 3 and 4, since 4 need to be migrated
        """
        if self.start_ver < 4:
            return

        self._perform_copy_list("User")

    def migrate_ReceiverTip(self):
        self._perform_copy_list("ReceiverTip")

    def migrate_WhistleblowerTip(self):
        self._perform_copy_list("WhistleblowerTip")

    def migrate_Comment(self):
        self._perform_copy_list("Comment")

    def migrate_InternalTip(self):
        self._perform_copy_list("InternalTip")

    def migrate_Receiver(self):
        self._perform_copy_list("Receiver")

    def migrate_InternalFile(self):
        self._perform_copy_list("InternalFile")

    def migrate_ReceiverFile(self):
        self._perform_copy_list("ReceiverFile")

    def migrate_Notification(self):
        self._perform_copy_single("Notification")

    def migrate_ReceiverContext(self):
        self._perform_copy_list("ReceiverContext")

    def migrate_ReceiverInternalTip(self):
        self._perform_copy_list("ReceiverInternalTip")

