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

from os.path import exists, splitext, basename, isfile
from os import remove
from qgis.server import QgsServerFilter
from qgis.core import (
    QgsProject,
    QgsMessageLog,
    QgsCoordinateReferenceSystem,
    QgsLayerTreeLayer,
    QgsVectorLayer,
    QgsRasterLayer)

from PyQt5.QtCore import QByteArray

from .tools import (
    generate_legend,
    validate_source_uri,
    is_file_path,
    layer_from_source)


class MapComposition(QgsServerFilter):

    """Class to create a QGIS Project with one or many layers."""

    def __init__(self, server_iface):
        super(MapComposition, self).__init__(server_iface)

    # noinspection PyPep8Naming
    def responseComplete(self):
        """Create a QGIS Project.

        Example :
        SERVICE=MAPCOMPOSITION&
        PROJECT=/destination/project.qgs&
        SOURCES=type=xyz&url=http://tile.osm.org/{z}/{x}/{y}.png?layers=osm;
            /path/1.shp;/path/2.shp;/path/3.asc&
        FILES={Legacy Name for Sources Parameter}
        NAMES=basemap;Layer 1;Layer 2;Layer 3&
        REMOVEQML=true&
        OVERWRITE=true&
        CRS=EPSG:4623&
        GROUP=group_name&
        """
        request = self.serverInterface().requestHandler()
        params = request.parameterMap()
        project = QgsProject.instance()

        if params.get('SERVICE', '').upper() == 'MAPCOMPOSITION':
            #request.clearHeaders()
            #QgsMessageLog.logMessage('current headers: %s' % str(request.responseHeaders()))
            request.setResponseHeader('Content-type', 'text/plain')
            request.clearBody()

            #QgsMessageLog.logMessage('params: %s' % str(params))
            project_path = params.get('PROJECT')
            if not project_path:
                request.appendBody(QByteArray('PROJECT parameter is missing.\n'.encode()))
                return

            overwrite = params.get('OVERWRITE')
            if overwrite:
                if overwrite.upper() in ['1', 'YES', 'TRUE']:
                    overwrite = True
                else:
                    overwrite = False
            else:
                overwrite = False

            remove_qml = params.get('REMOVEQML')
            if remove_qml:
                if remove_qml.upper() in ['1', 'YES', 'TRUE']:
                    remove_qml = True
                else:
                    remove_qml = False
            else:
                remove_qml = False
            

            if exists(project_path) and overwrite:
                # Overwrite means create from scratch again
                QgsMessageLog.logMessage( 'OVERWRITE: %s' % project_path )
                remove(project_path)
                project.clear()
                QgsMessageLog.logMessage( 'EXISTS' if exists(project_path) else 'NO EXISTS' )

            # Take datasource from SOURCES params
            sources_parameters = params.get('SOURCES')

            # In case SOURCES empty, maybe they are still using FILES.
            # Support legacy params: FILES.
            if not sources_parameters:
                sources_parameters = params.get('FILES')

            # In case FILES also empty, raise error and exit.
            if not sources_parameters:
                request.appendBody(QByteArray('SOURCES parameter is missing.\n'.encode()))
                return

            QgsMessageLog.logMessage('progress 0')

            sources = sources_parameters.split(';')
            for layer_source in sources:

                if not validate_source_uri(layer_source):
                    request.appendBody(QByteArray('invalid parameter: {0}.\n'.format(str(layer_source)).encode()))
                    return

                if is_file_path(layer_source):
                    if not exists(layer_source):
                        request.appendBody(QByteArray('file not found : {0}.\n'.format(str(layer_source)).encode()))
                        return
                        
            QgsMessageLog.logMessage('progress 1')

            names_parameters = params.get('NAMES', None)
            if names_parameters:
                names = names_parameters.split(';')
                if len(names) != len(sources):
                    request.appendBody(QByteArray('Not same length between NAMES and SOURCES'.encode()))
                    return
            else:
                names = [
                    splitext(basename(layer_source))[0]
                    for layer_source in sources]

            QgsMessageLog.logMessage('Setting up project to %s' % project_path)
            project.setFileName(project_path)
            if exists(project_path) and not overwrite:
                project.read()
            else:
                crs = params.get('CRS')
                QgsMessageLog.logMessage('CRS %s' % crs)
                if crs:
                    project.setCrs(QgsCoordinateReferenceSystem(crs))


            qml_files = []
            # Loaded QGIS Layer
            qgis_layers = []
            # QGIS Layer loaded by QGIS
            project_qgis_layers = []
            # Layer ids of vector and raster layers
            vector_layers = []
            raster_layers = []
            
            QgsMessageLog.logMessage('progress 2')

            for layer_name, layer_source in zip(names, sources):
                
                qgis_layer = layer_from_source(layer_source, layer_name)
                
                if not qgis_layer:
                    request.appendBody(QByteArray('Invalid format : {0}.\n'.format(layer_source).encode()))
                    return

                if not qgis_layer.isValid():
                    request.appendBody(QByteArray('Layer is not valid : {0}.\n'.format(layer_source).encode()))
                    return

                if isinstance(qgis_layer, QgsRasterLayer):
                    raster_layers.append(qgis_layer.id())
                elif isinstance(qgis_layer, QgsVectorLayer):
                    vector_layers.append(qgis_layer.id())
                else:
                    request.appendBody(QByteArray('Invalid type : {0} - {1}'.format(
                        qgis_layer, type(qgis_layer)).encode()))

                qgis_layers.append(qgis_layer)

                qml_file = splitext(layer_source)[0] + '.qml'
                if exists(qml_file):
                    # Check if there is a QML
                    qml_files.append(qml_file)

                style_manager = qgis_layer.styleManager()
                style_manager.renameStyle('', 'default')

            QgsMessageLog.logMessage('progress 3')

            map_registry = QgsProject.instance()
            # Add layer to the registry

            if overwrite:
                # Insert all new layers
                group = params.get('GROUP')
                QgsMessageLog.logMessage("GROUP " + group)
                if group:
                    legendRoot = QgsProject.instance().layerTreeRoot()
                    newgroup = legendRoot.insertGroup(0, group)
                    for lyr in qgis_layers:
                        map_registry.addMapLayer(lyr, False)
                        newgroup.insertChildNode(0, QgsLayerTreeLayer(lyr))
                        QgsMessageLog.logMessage("LEGEND " + lyr.id())
                else:
                    map_registry.addMapLayers(qgis_layers)
            else:
                # Updating rules
                # 1. Get existing layer by name
                # 2. Compare source, if it is the same, don't update
                # 3. If it is a new name, add it
                # 4. If same name but different source, then update
                for new_layer in qgis_layers:
                    # Get existing layer by name
                    current_layer = map_registry.mapLayersByName(
                        new_layer.name())

                    # If it doesn't exists, add new layer
                    if not current_layer:
                        map_registry.addMapLayer(new_layer)
                        project_qgis_layers.append(new_layer)
                    # If it is exists, compare source
                    else:
                        current_layer = current_layer[0]
                        project_qgis_layers.append(current_layer)

                        # Same source, don't update
                        if current_layer.source() == new_layer.source():
                            if isinstance(new_layer, QgsVectorLayer):
                                vector_layers.remove(new_layer.id())
                                vector_layers.append(current_layer.id())
                            elif isinstance(new_layer, QgsRasterLayer):
                                raster_layers.remove(new_layer.id())
                                raster_layers.append(current_layer.id())

                        # Different source, update
                        else:
                            QgsMessageLog.logMessage('Update {0}'.format(
                                new_layer.name()))
                            if isinstance(new_layer, QgsVectorLayer):
                                project.removeEntry(
                                    'WFSLayersPrecision', '/{0}'.format(
                                        current_layer.id()))

                            map_registry.removeMapLayer(current_layer.id())
                            map_registry.addMapLayer(new_layer)


            QgsMessageLog.logMessage('progress 4')

            qgis_layers = [l for l in map_registry.mapLayers().values()]
            
            #QgsMessageLog.logMessage('loaded layers: %s' % str(qgis_layers))
            
            if len(vector_layers):
                for layer_source in vector_layers:
                    project.writeEntry(
                        'WFSLayersPrecision', '/%s' % layer_source, 8)
                project.writeEntry('WFSLayers', '/', vector_layers)

            if len(raster_layers):
                project.writeEntry('WCSLayers', '/', raster_layers)
                
            QgsMessageLog.logMessage('progress 5')

            project.write()
            #project.clear()

            if not exists(project_path) and not isfile(project_path):
                request.appendBody(QByteArray(project.error().encode()))
                return
                
            QgsMessageLog.logMessage('progress 6')

            #generate_legend(qgis_layers, project_path)
            
            QgsMessageLog.logMessage('progress 7')

            if remove_qml:
                for qml in qml_files:
                    QgsMessageLog.logMessage(
                        'Removing QML {path}'.format(path=qml))
                    remove(qml)
                    
            QgsMessageLog.logMessage('progress 8')
            request.setResponseHeader('Content-type', 'text/xml')
            request.clearBody()
            with open(project_path,"r") as xml_file:
                project_xml = xml_file.read()
            request.appendBody(QByteArray(project_xml.encode()))
            request.setStatusCode(200)
            QgsMessageLog.logMessage('progress 9')
            request.sendResponse()
