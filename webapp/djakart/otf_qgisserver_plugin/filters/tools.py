# -*- coding: utf-8 -*-

"""
***************************************************************************
    OTF QGIS Project
    ---------------------
    Date                 : June 2016
    Copyright            : (C) 2016 by Etienne Trimaille
    Email                : etienne at kartoza dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
import os
import urllib
from urllib.parse import urlparse,unquote,parse_qs
import xml.etree.ElementTree as ET

from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsMapLayer, QgsMessageLog, QgsDataSourceUri


def generate_legend(layers, project):
    """Regenerate the XML for the legend.

    QGIS Server itself is broken to generate a project as it's need a
    GUI to generate a correct project. We need to update the XML manually.

    :param layers: List of layers in the project to include in the legend.
    :type layers: list(QgsMapLayer)

    :param project: The project path to update.
    :type project: basestring
    """
    xml_string = '<legend updateDrawingOrder="true"> \n'
    for layer in layers:
        xml_string += '<legendlayer drawingOrder="-1" ' \
                      'open="true" checked="Qt::Checked" ' \
                      'name="%s" showFeatureCount="0"> \n' \
                      '<filegroup open="true" hidden="false"> \n' \
                      '<legendlayerfile isInOverview="0" ' \
                      'layerid="%s" visible="1"/> \n' \
                      '</filegroup>\n</legendlayer>\n' \
                      % (layer.name(), layer.id())
    xml_string += '</legend>\n'
    xml_legend = ET.fromstring(xml_string)
    document = ET.parse(project)
    xml_root = document.getroot()
    xml_root.append(xml_legend)
    document.write(project)


def is_file_path(uri):
    """True if this is a file path.

    :param uri: The uri to check
    :type uri: basestring

    :return: Boolean value
    :rtype: bool
    """
    try:
        # light checking, if it starts with '/',
        # then it is probably a file path
        if uri.startswith('/'):
            return True
        # Check if it is a proper file:// uri.
        # Need to unquote/decode it first
        sanitized_uri = unquote(uri)
        if sanitized_uri.startswith('file://'):
            return True
    except Exception:
        return False


def is_tile_path(uri):
    """True if this is a tile path.

    :param uri: The uri to check
    :type uri: basestring

    :return: Boolean value
    :rtype: bool
    """
    try:
        # Since this is a uri, unquote/decode it first
        sanitized_uri = unquote(uri)
        if sanitized_uri.startswith(('http://', 'https://')):
            return True
        # It might be in the form of query string
        query_params = parse_qs(sanitized_uri)
        query_params_keys = [k.lower() for k in query_params.keys()]
        if 'url' in query_params_keys:
            return True
    except Exception as E:
        QgsMessageLog.logMessage('Error: ' + str(E))
        return False

def is_pg_path(uri):
    sanitized_uri = unquote(uri)
    query_params = parse_qs(sanitized_uri)
    query_params_keys = [k.lower() for k in query_params.keys()]
    print (sanitized_uri, query_params, query_params_keys) 
    QgsMessageLog.logMessage('sanitized_uri: ' + sanitized_uri)
    if 'dbname' in query_params_keys : #and 'host' in query_params_keys and 'port' in query_params_keys
        return True
    else:
        return False

def validate_source_uri(source_uri):
    """Validate a given source uri.

    A source URI for QgsMapLayer is valid if it is a file path:
    e.g. "/path/to/layer.shp"
    or a WMS/Tile request
    e.g. "type=xyz&url=http://tile.osm.org/{z}/{x}/{y}.png?layers=osm"

    :param source_uri: A source URI
    :type source_uri: basestring

    :return: Boolean value
    :rtype: bool
    """
    #QgsMessageLog.logMessage('validating URI: %s %s' % ( source_uri , str(is_file_path(source_uri) or is_tile_path(source_uri) or is_pg_path(source_uri))))
    return is_file_path(source_uri) or is_tile_path(source_uri) or is_pg_path(source_uri)


def layer_from_source(source_uri, name):
    """Return QgsMapLayer from a given source uri.

    :param source_uri: A source URI
    :type source_uri: basestring

    :param name: Designated layer name
    :type name: basestring

    :return: QgsMapLayer
    :rtype: qgis.core.QgsMapLayer
    """
    vector_extensions = ('shp', 'geojson')
    raster_extensions = ('asc', 'tiff', 'tif', 'geotiff', 'geotif')
    qlr_extensions = ('qlr', )

    qgis_layer = None

    if is_file_path(source_uri):

        # sanitize source_uri
        sanitized_uri = unquote(source_uri)
        sanitized_uri.replace('file://', '')

        if source_uri.endswith(vector_extensions):
            qgis_layer = QgsVectorLayer(sanitized_uri, name, 'ogr')

        elif source_uri.endswith(raster_extensions):
            qgis_layer = QgsRasterLayer(sanitized_uri, name)

        elif source_uri.endswith(qlr_extensions):

            qgis_layer = QgsMapLayer.fromLayerDefinitionFile(sanitized_uri)
            if qgis_layer:
                qgis_layer = qgis_layer[0]
                qgis_layer.setName(name)
    
    elif is_pg_path(source_uri):
        sanitized_uri = unquote(source_uri)
        query_params = parse_qs(sanitized_uri)
        uri = QgsDataSourceUri()
        uri.setConnection(query_params["host"][0], query_params["port"][0], query_params["dbname"][0], None, None)
        uri.setPassword(query_params["password"][0])
        uri.setUsername(query_params["user"][0])
        uri.setSchema(query_params["schema"][0])
        uri.setTable(query_params["table"][0])
        if "geom_field" in query_params:
            uri.setGeometryColumn(query_params["geom_field"][0])
        if "key_field" in query_params:
            uri.setKeyColumn(query_params["key_field"][0])
        if "checkPrimaryKeyUnicity" in query_params:
            uri.setParam("checkPrimaryKeyUnicity",query_params["checkPrimaryKeyUnicity"][0])
        if "sql" in query_params:
            uri.setSql(unquote(query_params["sql"][0]))
        QgsMessageLog.logMessage('PG URI:',uri.uri())
        qgis_layer = QgsVectorLayer(uri.uri(), query_params["table"][0], 'postgres')
        

    elif is_tile_path(source_uri):

        # sanitize source_uri
        sanitized_uri = unquote(source_uri)
        # Check if it is only a url
        if sanitized_uri.startswith(('http://', 'https://')):
            # Then it is probably a tile xyz url
            sanitized_uri = 'type=xyz&url={0}'.format(sanitized_uri)
        # It might be in the form of query string
        query_params = parse_qs(sanitized_uri)
        driver = query_params.get('driver', 'wms')
        qgis_layer = QgsRasterLayer(sanitized_uri, name, driver)

    

    return qgis_layer
