#defaults
from django.conf import settings
from django.db import connections

import os
import subprocess
import json
import re
import requests
import sys

KART_EXE = "/opt/kart/kart_cli"

PG_SU = os.environ.get("POSTGRES_USER", "blabla")

KART_SU = os.environ.get("VERSION_ADMIN", "blabla")
KART_SU_PWD = os.environ.get("VERSION_ADMIN_PASSWORD", "blabla")

KART_PGUSER = os.environ.get("VERSION_VIEWER", "blabla")
KART_PGUSER_PWD = os.environ.get("VERSION_VIEWER_PASSWORD", "blabla")

SRID = os.environ.get("REPO_CRS")
SRID_CODE = SRID.split(":")[1]

class KartException(Exception):
    pass

def executeCmd(commands, cmd=False, path=None, jsonoutput=False, feedback=None):
    if not cmd:
        commands.insert(0, KART_EXE)
    if jsonoutput:
        commands.append("-ojson")

    # The env PYTHONHOME from QGIS can interfere with Kart.
    if not hasattr(executeCmd, "env"):
        executeCmd.env = os.environ.copy()
        if "PYTHONHOME" in executeCmd.env:
            executeCmd.env.pop("PYTHONHOME")

    # always set the use helper env var as it is long lived and the setting may have changed
    #executeKart.env['KART_USE_HELPER'] = '1' if setting(HELPERMODE) else ''

    try:
        encoding = "utf-8" #locale.getdefaultlocale()[1] or 
        with subprocess.Popen(
            commands,
            #shell=os.name == "nt",
            env=executeCmd.env,
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding=encoding,
            cwd=path,
        ) as proc:
            if feedback is not None:
                output = []
                err = []
                for line in proc.stderr:
                    feedback(line)
                    err.append(line)
                for line in proc.stdout:
                    output.append(line)
                stdout = "".join(output)
                stderr = "".join(err)
                proc.communicate()  # need to get the returncode
            else:
                stdout, stderr = proc.communicate()
            if proc.returncode:
                print (stderr)
                raise KartException(stderr)
                return "error: " + stderr
            if jsonoutput:
                return json.loads(stdout)
            else:
                return stdout
    except Exception as e:
        print ("commands",commands)
        print ("kart exception",str(e))
        raise KartException(str(e))
        return "error: " + str(e)

def crea_fdw(nuova_versione):

    crea_fdw_template = """
CREATE FOREIGN TABLE IF NOT EXISTS "{schema}".pua(
    gid integer NULL,
    id_pua character(5) NULL COLLATE pg_catalog."default",
    the_geom geometry(MultiPolygon,{crs}) NULL
)
    SERVER istanze
	OPTIONS (schema_name 'public', table_name 'pua');

ALTER FOREIGN TABLE "{schema}".pua
    OWNER TO "{admin}";

GRANT ALL ON TABLE "{schema}".pua TO "{admin}";

GRANT SELECT ON TABLE "{schema}".pua TO "{user}";

GRANT ALL ON TABLE "{schema}".pua TO postgres;
    """

    cursor = connections['versions'].cursor()

    cursor = connections['versions'].cursor()

    common_params = {
        "admin": KART_SU,
        "user": KART_PGUSER,
        "crs": SRID
    }

    try:
        print (crea_fdw_template.format(**common_params, schema=nuova_versione))
        cursor.execute(crea_fdw_template.format(**common_params, schema=nuova_versione))
        return True
    except Exception as e:
        print(e)
        cursor.execute(crea_fdw_template.format(**common_params, schema=nuova_versione+"_pub"))
        return None

def crea_pg_schema(nuova_versione, readonly=False):

    if readonly:
        schema_owner = PG_SU
    else:
        schema_owner = KART_SU

    crea_schema_template = '''
CREATE SCHEMA IF NOT EXISTS "{schema}" AUTHORIZATION "{owner}";    
    '''

    cursor = connections['versions'].cursor()
    try:
        print (crea_schema_template.format(schema=nuova_versione, owner=schema_owner))
        cursor.execute(crea_schema_template.format(schema=nuova_versione, owner=schema_owner))
        return True
    except Exception as e:
        print(e)
        return None

def grant_select_schema(versione, schema_user=KART_PGUSER, schema_admin=KART_SU):

    grant_select_template = '''
GRANT USAGE ON SCHEMA "{schema}" TO "{user}";
GRANT ALL ON SCHEMA "{schema}" TO "{admin}";
GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO "{user}";   
GRANT ALL ON ALL TABLES IN SCHEMA "{schema}" TO "{admin}";   
    '''

    cursor = connections['versions'].cursor()
    try:
        cursor.execute(grant_select_template.format(
            schema=versione, 
            admin=schema_admin,
            user=schema_user
        ))
        return True
    except Exception as e:
        print(e)
        cursor.execute(grant_select_template.format(
            schema=versione+"_pub", 
            admin=schema_admin,
            user=schema_user
        ))
        return None

def elimina_pg_schema(nuova_versione):

    schema_owner = KART_SU
    canc_schema_template = '''
DROP SCHEMA IF EXISTS "{schema}" CASCADE   
    '''

    cursor = connections['versions'].cursor()
    try:
        cursor.execute(canc_schema_template.format(schema=nuova_versione, owner=schema_owner))
        return True
    except Exception as e:
        print(e)
        return None

def crea_nuovo_repository(repo_name,bare=True,readonly_workingcopy=None):
    repo_path = os.path.join(settings.KART_REPO,repo_name)
    cmds = ["init", repo_path]
    if readonly_workingcopy:
        crea_pg_schema(readonly_workingcopy, readonly=True)
        cmds.append("--workingcopy-location")
        cmds.append("postgresql://{user}:{password}@{host}:{port}/{db}/{schema}".format(
            user=KART_SU,
            password=KART_SU_PWD,
            host=os.environ.get("POSTGRES_SERVER",'pgserver'),
            port=os.environ.get("POSTGRES_PORT",'pgport'),
            db=os.environ.get("VERSION_DB",'pgdb'),
            schema=readonly_workingcopy
        ))
    if bare:
        cmds = ["init", "--bare", repo_path]
    if not os.path.exists(repo_path):
        cmd = executeCmd(cmds)
        return cmd
    

def crea_nuova_versione(nuova_versione,base,tipo="pg"):
    nuova_versione_path = os.path.join(settings.KART_REPO,nuova_versione)
    master_path = os.path.join(settings.KART_REPO,base)
    if tipo == 'pg':
        crea_pg_schema(nuova_versione)
        uri = "postgresql://{user}:{password}@{host}:{port}/{db}/{schema}".format(
            user=KART_SU,
            password=KART_SU_PWD,
            host=os.environ.get("HOST_EXTERNAL",'pgserver'),
            port=os.environ.get("POSTGRES_PORT_EXTERNAL",'pgport'),
            db=os.environ.get("VERSION_DB",'pgdb'),
            schema=nuova_versione
        )
    elif tipo == 'gp':
        uri = "" #local geopackage
    if not os.path.exists(nuova_versione_path):
        if not base:
            init_cmd = executeCmd(["init", nuova_versione_path])
        else:
            #clone master
            clone_cmd = executeCmd(["clone", master_path, nuova_versione_path])
            new_branch = executeCmd(["--repo",nuova_versione_path,"checkout", "-b", nuova_versione])
        new_wc = executeCmd(["--repo",nuova_versione_path,"create-workingcopy", '--delete-existing', uri])
        grant_select_schema(nuova_versione)
        #crea_fdw(nuova_versione)
        serial_pk_setup(nuova_versione)

def merge_versione(versione, abort=False, confirm=False):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        #clone master
        #commit_versione(versione, '"merge %s"' % versione)
        if abort:
            abort_cmd = executeCmd(["--repo", versione_path, "merge", "--abort"])
        elif confirm:
            status = json.loads(status_versione(versione, as_json=True))
            theirs = status["kart.status/v2"]["merging"]["theirs"]
            versione_merging = theirs.get("branch") or theirs.get("abbrevCommit")
            confirm_cmd = executeCmd(["--repo", versione_path, "merge", "--continue","-m","merge %s con risoluzione conflitti" % versione_merging])
        else:
            master_path = get_remote(versione)
            master_versione = os.path.split(master_path)[-1]
            push_cmd = executeCmd(["--repo", versione_path, "push", "origin", versione])
            #chkout_cmd = executeKart(["--repo", master_path, "checkout", "main"])
            merge_cmd = executeCmd(["--repo",master_path,"merge","-m","merge "+versione, versione])
            if ("Nothing to commit, working copy clean" in status_versione(master_path)) or ("No working copy" in status_versione(master_path)):
                #non dovrebbe cancellare branch con conflitti in fase di merge
                delete_branch_cmd = executeCmd(["--repo",master_path,"branch","-d",versione])
            grant_select_schema(master_versione)
            grant_select_schema(versione)

def clone_versione(versione, target):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        clone_cmd = executeCmd(["clone", versione_path, target])

def config_user_versione(versione, username, useremail):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        setuser = kart_cmd(versione_path, ["config", "user.name", username])
        setmail = kart_cmd(versione_path, ["config", "user.email", useremail])

def aggiorna_riferimenti(versione):
    """
    lascio per eredità di documentazione
    serviva per aggiornare i repository collegati _pub _export
    adesso non serve più perchè i repository collegati sono stati abbandonati
    """
    fetch_args = ["fetch", "--quiet", "origin", "main"]
    reset_arg = ["reset", "FETCH_HEAD"]
    res = []
    res.append(kart_cmd(versione+"_export",fetch_args))
    res.append(kart_cmd(versione+"_export",reset_arg))
    res.append(kart_cmd(versione+"_pub",fetch_args))
    res.append(kart_cmd(versione+"_pub",reset_arg))

def pull_versione(versione):  
    versione_path = os.path.join(settings.KART_REPO,versione)
    #master_path = get_remote(versione)
    if os.path.exists(versione_path):
        push_cmd = executeCmd(["--repo", versione_path, "pull", "origin"])

def kart_cmd(versione,args):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        kart_cmd = executeCmd(["--repo", versione_path] + args)
        return kart_cmd

def importa_dataset(versione,ds_path,max_extent=None):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        if not max_extent:
            max_extent = [sys.float_info.max, sys.float_info.max, -sys.float_info.max, -sys.float_info.max]
        #EXTRACT EXTENT
        ogrinfo_pass1 = executeCmd(["/usr/bin/ogrinfo", ds_path],cmd=True)
        #^[0-9]+: .*$
        print("ogrinfo_pass1",ogrinfo_pass1)
        lyrs = []
        for group in re.findall(r"^[0-9]+: .*(?=\()", ogrinfo_pass1, flags=re.MULTILINE):
            print (group)
            lyrs.append(group)
            clean_group = group.split(":")[-1].strip()
            ogrinfo_pass2 = executeCmd(["/usr/bin/ogrinfo", "-so", ds_path, clean_group],cmd=True)
            extent_row = re.findall(r"^Extent.*$",ogrinfo_pass2, flags=re.MULTILINE)
            if extent_row:
                extent_json = extent_row[0].replace("Extent: (","[").replace(") - (",", ").replace(")","]")
                extent = json.loads(extent_json)
                print ("group %s %s" % (group, extent))
                if extent[0] < max_extent[0]:
                    max_extent[0] = extent[0]
                if extent[1] < max_extent[1]:
                    max_extent[1] = extent[1]
                if extent[2] > max_extent[2]:
                    max_extent[2] = extent[2]
                if extent[3] > max_extent[3]:
                    max_extent[3] = extent[3]

        print ("MAXEXTENT", max_extent)

        importa_cmd = executeCmd(["--repo", versione_path, "import", "--replace-existing", "-a", ds_path])
        grant_select_schema(versione)
        
        return max_extent

def commit_versione(versione, messaggio):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        #recover_uncommitted_nulls(versione) #necessario per evitare successive exceptions di kart
        commit_cmd = executeCmd(["--repo", versione_path, "commit", "-m", messaggio])

def elimina_versione(canc_versione):
    canc_versione_path = os.path.join(settings.KART_REPO,canc_versione)
    pgschema = elimina_pg_schema(canc_versione)
    if os.path.exists(canc_versione_path):
        #clone master
        if pgschema:
            rm_cmd = executeCmd(["rm","-Rf",canc_versione_path],cmd=True)
        else:
            print ("ERRORE elimina pg_uri")
    
    
def undo_commit_versione(versione, force=None):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        jlog = log_versione(versione,jsonoutput=True)
        hash = jlog[1]["commit"]
        if force:
            cmd = executeCmd(["--repo",versione_path,"reset","--force",hash])
        else:
            cmd = executeCmd(["--repo",versione_path,"reset",hash])
        return cmd
    
def restore_versione(versione):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        cmd = executeCmd(["--repo",versione_path,"restore"])
        return cmd
    
def status_versione(versione, as_json=False):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        try:
            params = ["--repo",versione_path,"status"]
            if as_json:
                params = params + ["-o", "json"]
            cmd = executeCmd(params)
            return cmd
        except KartException as E:
            return str(E)
    else:
        return ""
    
def show_versione(versione, jsonoutput=False):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        cmd = executeCmd(["--repo",versione_path,"show"], jsonoutput=jsonoutput)
        merged_list = cmd.replace("* ","").replace("  ","").split("\n")
        return merged_list

def merged_list_versione(versione):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        try:
            cmd = executeCmd(["--repo",versione_path,"branch","--merged"], jsonoutput=False)
            return cmd
        except Exception as E:
            print (E)
            return [str(E)]

def log_versione(versione, jsonoutput=False):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        cmd = executeCmd(["--repo",versione_path,"log"], jsonoutput=jsonoutput)
        return cmd
    

def genera_diff_versione(versione, hash=None, prev=None, format='html'):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        jlog = log_versione(versione,jsonoutput=True)
        commit = list(filter(lambda target: target["commit"] == hash, jlog))
        if commit and not prev:
            prev = commit[0]["parents"][0] 
        if format == 'html':
            #diff_template_location = os.path.join(os.path.dirname(os.path.realpath(__file__)),'diff-view.html')
            response = requests.get("http://localhost:8000/djakart/diff-view/%s/" % versione)
            print (response.text)
            with open("/tmp/diff-view.html", "w", encoding="utf8") as diff_template:
                diff_template.write(response.text)
            if hash == 'HEAD':
                cmd = executeCmd(["--repo",versione_path,"diff","-o","html", "--html-template", '/tmp/diff-view.html', "--crs", SRID, "--output", "-", hash])
            else:
                cmd = executeCmd(["--repo",versione_path,"diff","-o","html", "--html-template", '/tmp/diff-view.html', "--crs", SRID, "--output", "-", prev, hash])
        elif format == 'json':
            cmd = executeCmd(["--repo",versione_path,"diff","-o","json", "--output", "-", hash])
        return cmd
    
def conflitti_versione(versione):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        conflicts_dir = os.path.join(versione_path,'conflicts')
        cmd = executeCmd(["--repo",versione_path,"conflicts", "--crs", SRID,"-o","geojson","--output",conflicts_dir])
        feats = []
        for gj in os.listdir(conflicts_dir):
            conflict_path = os.path.join(conflicts_dir,gj)
            with open (conflict_path,'r') as gjf:
                feats = feats + json.loads(gjf.read())["features"]
            os.remove(conflict_path)

        return {
                "type": "FeatureCollection",
                "features": feats
        }
    
def resolve_conflitto(versione, tag_conflitto, risoluzione):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        cmd = executeCmd(["--repo",versione_path,"resolve","--with",risoluzione,tag_conflitto])
        return cmd

def get_remote(versione, remote="origin", method='push'):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        cmd = executeCmd(["--repo",versione_path,"remote","-v"])
        if cmd:
            q = "(?<={})([^\n]*)(?=\({}\))".format(remote,method)
            test = re.search(q, cmd)
            return test.group(0).strip() if test.group(0) else None

def list_versioned_tables(versione):
    versione_path = os.path.join(settings.KART_REPO,versione.replace("_pub",""))
    if os.path.exists(versione_path):
        cmd = executeCmd(["--repo",versione_path,"data","ls"])
        ds_list = cmd.split("\n")
        return [ds for ds in ds_list if ds != ""]

def prevent_conflicts_on_ids(versione):
    cursor = connections['versions'].cursor()
    for table in list_versioned_tables(versione):
        stepoverseq = ""

def geo_tables(versione):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        geom_tables = []
        for tab in list_versioned_tables(versione):
            cmd = executeCmd(["--repo",versione_path,"meta","get",tab])
            capture = re.search("""(?<=(schema.json\n))(\w|\d|\n|[().,\-:;@#$%^&*\[\]"'+–®°⁰!?{}|`~]| )+?(?=(\]))""", cmd)
            if capture:
                tab_meta = json.loads(capture[0]+"]")
                for prop in tab_meta:
                    if prop.get("dataType") == "geometry":
                        geom_tables.append(tab)
        return geom_tables

def get_metadata(versione,tab):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        try:
            cmd = executeCmd(["--repo",versione_path,"meta","get",tab,"-o","json"])
            return json.loads(cmd)
        except KartException as E:
            return {"error":True,"result":str(E)}

def get_schema(versione,tab,**kwargs):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        metadata = get_metadata(versione,tab)
        schema = {}
        if not "error" in metadata.keys():
            for item in metadata[tab]["schema.json"]:
                if kwargs:
                    if item[list(kwargs.keys())[0]] == list(kwargs.values())[0]:
                        schema[item["name"]] = item
                else:
                    schema[item["name"]] = item
        return schema

def recover_uncommitted_nulls(versione):
    versione_path = os.path.join(settings.KART_REPO,versione)
    if os.path.exists(versione_path):
        cmd = kart_cmd(versione,['diff','-o','json'])
        uncommitted_diff = json.loads(cmd)
        corrs = []
        for ds,details in uncommitted_diff["kart.diff/v1+hexwkb"].items():
            integer_fields = get_schema(versione,ds,dataType="integer")
            numeric_fields = get_schema(versione,ds,dataType="numeric")
            check_fields = {**integer_fields,**numeric_fields}
            check_fields.pop("auto_pk",None)
            for update in details["feature"]:
                for numfield in check_fields.keys():
                    #print (numfield, numfield in update["+"], ":",update["+"].get(numfield), type(update["+"].get(numfield)))
                    if update["+"].get(numfield) in ("", None):
                        corrs.append({
                            "schema": versione,
                            "table": ds,
                            "field": numfield,
                            "value": 0
                        })
        if corrs:
            sql = ""
            for corr in corrs:
                sql += 'UPDATE "{schema}"."{table}" SET "{field}" = {value};\n'.format(**corr)
            cursor = connections['versions'].cursor()
            cursor.execute(sql)

def get_schemas():
    sql = """ SELECT nspname FROM pg_catalog.pg_namespace;"""
    cursor = connections['versions'].cursor()
    cursor.execute(sql)
    return [row[0] for row in cursor.fetchall()]

def get_sequences(schema):
    sql = """SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = '{schema}' """.format(schema=schema)
    cursor = connections['versions'].cursor()
    cursor.execute(sql)
    return [row[0] for row in cursor.fetchall()]

def serial_pk_setup(versione, aumento=100):
    cursor = connections['versions'].cursor()
    base_path = get_remote(versione)
    base = os.path.split(base_path)[-1]
    if base:
        schemas = get_schemas()
        #if not base in schemas:
        #    base = base + "_pub"
        #    if not base in schemas:
        #        raise KartException
        sequences = get_sequences(base.replace("_pub",""))
        print (list_versioned_tables(base))
        print (base)
        for tab in list_versioned_tables(base):
            if not (tab + "_auto_pk_seq") in sequences:
                continue
            #sql = """SELECT MAX(auto_pk) from "{schema}"."{table}";""".format(schema=versione,table=tab)
            sql = """SELECT last_value FROM "{schema}"."{table}_auto_pk_seq";""".format(schema=base,table=tab)
            cursor.execute(sql)
            min_pk = cursor.fetchone()[0]
            min_pk += 100
            sql = """ALTER SEQUENCE "{schema}"."{table}_auto_pk_seq" RESTART WITH {val}""".format(schema=versione, table=tab, val=min_pk)
            cursor.execute(sql)
            sql = """ALTER SEQUENCE "{schema}"."{table}_auto_pk_seq" RESTART WITH {val}""".format(schema=base, table=tab, val=min_pk)
            cursor.execute(sql)


