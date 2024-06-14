from django.urls import path, include, re_path
from . import views

from django.conf import settings
import django.contrib.auth.views

__author__ = "Enrico Ferreguti"
__email__ = "enricofer@gmail.com"
__copyright__ = "Copyright 2017, Enrico Ferreguti"
__license__ = "GPL3"

urlpatterns = [
    re_path(r'^log/(\w+)/$', views.log, name='log'),
    re_path(r'^status/(\w+)/$', views.status, name='status'),
    re_path(r'^vlist/(\d+)/$', views.vlist, name='vlist'),
    re_path(r'^show/(\w+)/$', views.show, name='status'),
    re_path(r'^qgs/(\w+)/$', views.QGS_progetto, name='qgs'),
    re_path(r'^basemaps/(background|foreground)/$', views.basemaps_js, name='basemaps'),
    re_path(r'^diff-view/(\w+)/$', views.diff_view, name='diffview'),
    re_path(r'^diff\/(?P<versione>\w+)\/(?P<hash>\w+)\/((?P<parent_hash>\w+)?\/)?$', views.diff, name='diff'),
    #url(r'^diff/(?P<versione>\w+)/(?P<parent_hash>\w+)/(?P<parent_hash>\w+)/$', views.diff, name='diff'),
    #re_path(r'^login/', django.contrib.auth.views.LoginView),
    #re_path(r'^logout/', django.contrib.auth.views.LogoutView),
]