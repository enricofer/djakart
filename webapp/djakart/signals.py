# signals.py
from django.db.models.signals import post_save, pre_delete, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from django.db import connections
import os

@receiver(m2m_changed, sender=User)
@receiver(pre_delete, sender=User)
@receiver(post_save, sender=User)
def on_user_model_change(*args, **kwargs):
    sync_usermapping()

def sync_usermapping():
    cursor = connections['backoffice'].cursor()
    user_tmp = """CREATE ROLE "{username}" WITH LOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{pwd}'; GRANT "{adm}" TO "{username}";"""
    
    cursor.execute("select usename from pg_user_mappings")
    for row in cursor.fetchall():
        username = row[0]
        if not username in [os.environ.get("POSTGRES_USER", ""), os.environ.get("POSTGRES_USER", ""),]:
            cursor.execute("""DROP USER MAPPING IF EXISTS FOR "{user}" SERVER {server};""".format(user=username, server=os.environ.get("POSTGRES_DB", "")))
            print (username, "dropped")
    
    for user in User.objects.all().exclude(username=os.environ.get("DJANGO_SUPERUSER_USERNAME", "")):
        print ("create user mapping", user)
        try:
            cursor.execute(user_tmp.format(username=user.username, pwd="q908ehcfqw9eun9", adm=os.environ.get("VERSION_ADMIN", "")))
        except:
            print ("user", user.username, "exists")
            pass
        try:
            cursor.execute("""CREATE USER MAPPING FOR "{user}" SERVER {server} OPTIONS ("user" '{edituser}', password '{editpwd}');""".format( 
                user=user.username,
                server=os.environ.get("POSTGRES_DB", ""),
                edituser=os.environ.get("VERSION_ADMIN", ""),
                editpwd=os.environ.get("VERSION_ADMIN_PASSWORD", "")
            ))
        except Exception as E:
            print (E)
            print ("user mapping", user, "exists")
            pass