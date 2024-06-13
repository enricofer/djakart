console.log('FINESTRAMAPPA LOADING')

var targetExtent = [1716014, 5023919, 1737137, 5038662];

var map_glob, getfeature_popup;
var polyObject, zoningObject //polyJSON, zoningJSON, 
var polyFeatures, polyOverlaysx, polyOverlaydx, currentOverlay, versionOverlay, dbtOverlay;

var targetProjection = new ol.proj.Projection({
    code: CRSID,
    // The extent is used to determine zoom level 0. Recommended values for a
    // projection's validity extent can be found at http://epsg.io/.
    extent: targetExtent,
    units: 'm'
});
ol.proj.addProjection(targetProjection);

var UTM32Extent = [719459.961,5024860.053, 733523.921,5038269.875];
proj4.defs('EPSG:32632', '+proj=utm +zone=32 +datum=WGS84 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs');
var UTM32proj = new ol.proj.Projection({
    code: 'EPSG:32632',
    extent: UTM32Extent
});
ol.proj.addProjection(UTM32proj);

var ETRS89Extent = [719459.961,5024860.053, 733523.921,5038269.875];
proj4.defs('EPSG:25832', '+proj=utm +zone=32 +ellps=GRS80 +towgs84=128.8,17.85,0,0,0,0,0 +units=m +no_defs');
var ETRS89proj = new ol.proj.Projection({
    code: 'EPSG:25832',
    extent: ETRS89Extent
});
ol.proj.addProjection(ETRS89proj);

var geoJson_convertitore = new ol.format.GeoJSON();

var WKT_convertitore = new ol.format.WKT();

/**
 * @param {number} n The max number of characters to keep.
 * @return {string} Truncated string.
 */
String.prototype.trunc = String.prototype.trunc ||
    function(n) {
    return this.length > n ? this.substr(0, n - 1) + '...' : this.substr(0);
    };

function copia_clipboard (txt) {
    var $temp = $("<input>");
    $("body").append($temp);
    $temp.val(txt).select();
    document.execCommand("copy");
    $temp.remove();
    alert("Testo copiato negli appunti:\n"+txt)
}

function hideGeom( ) {
    console.log("hideGeom è ORA")
    $( "h2:contains('localizzazione_mod')" ).parent().hide()
}

window.app = {};
var app = window.app;


function loadFinestraMappa( polyWKT) { 

    console.log(versioni_wms)

    var base_wms = versioni_wms[1]["wms"]
    var versione_wms = versioni_wms[0]["wms"]

    console.log("ONLOAD è ORA")
    $( "h2:contains('posizione_mod')" ).parent().hide()
    
    var maxResolution = 10;

    function getText(feature, resolution) {
        var text;
        if (resolution > maxResolution) {
            text = '';
        } else {
            text = feature.get('id_pua').toString()+"\n"+feature.get('ditta').trunc(20);;
        }
        return text;
    }

    function polygonStyleFunction(feature, resolution) {
        console.log(feature.get('idIstanza'));
        console.log(resolution);
        return new ol.style.Style({
            stroke: new ol.style.Stroke({
                color: '#ff0000',
                width: 3
            }),
            fill: new ol.style.Fill({
                color: 'rgba(255, 255, 255, 0.3)'
            }),
        });
    }

    //particelle overlay
    let slider
    let multipolygon
    window.currentID = 99999
    if (polyWKT) {
        multipolygon = new ol.format.WKT().readGeometry(polyWKT)
        polyFeatures = new ol.Collection();
        slider = 0.5

        if (multipolygon.getPolygons().length > 1) {
            for (var i = 0; i < multipolygon.getPolygons().length; i++) {
                let newFeat = new ol.Feature({
                    geometry: multipolygon.getPolygon(i),
                    part: i,
                    id: i,
                });
                polyFeatures.push(newFeat)
            }
            currentID = i
        } 
    
        window.multiID = currentID
    
        polyFeatures.push(new ol.Feature({
            geometry: multipolygon,
            part: currentID,
            id: currentID
        }))

    }
    else {
        polyFeatures = new ol.Collection()
        slider = 0
    }

    polyOverlaysx = new ol.layer.Vector({
        source: new ol.source.Vector({
            features: polyFeatures
        }),
        title: 'perimetro relativo alla richiesta',
        style: polygonStyleFunction
    });

    polyOverlaydx = new ol.layer.Vector({
        source: new ol.source.Vector({
            features: polyFeatures
        }),
        title: 'perimetro relativo alla richiesta',
        style: polygonStyleFunction
    });
    console.log("base_wms",base_wms)
    if (base_wms == "") {
        console.log("Pubblicazione ol.source.TileArcGISRest")
        currentOverlay = new ol.layer.Tile({
            extent: targetExtent,
            title: 'DBT',
            visible: true,
            source: new ol.source.TileArcGISRest({
              url: 'https://oscar.comune.padova.it/server/rest/services/dbt/MapServer',
              params: {
                'LAYERS':"show:",
                'DPI':150,
                //'TRANSPARENT': 'true'
              },
            }),
          })
    } else {
        currentOverlay = new ol.layer.Tile({
            extent: targetExtent,
            title: 'DBT BASE',
            visible: true,
            source: new ol.source.TileWMS({
              url: base_wms,
              params: {layers: 'VERSIONE',CRS:'EPSG:3003','DPI':150}
            })
          })
    }

    dbtOverlaySx = new ol.layer.Tile({
    extent: targetExtent,
    title: 'DBT base light',
    visible: true,
    source: new ol.source.TileWMS({
        url: 'https://rapper.comune.padova.it/mapproxy/',
        params: {layers: 'PI2030_base',CRS:'EPSG:3003','DPI':150}
      })
    })

    dbtOverlayDx = new ol.layer.Tile({
    extent: targetExtent,
    title: 'DBT versione light',
    visible: true,
    source: new ol.source.TileWMS({
        url: 'https://rapper.comune.padova.it/mapproxy/',
        params: {layers: 'PI2030_base',CRS:'EPSG:3003','DPI':150}
      })
    })

    versionOverlay = new ol.layer.Tile({
      extent: targetExtent,
      title: 'DBT VERSIONE',
      visible: true,
      source: new ol.source.TileWMS({
        url: versione_wms,
        params: {layers: 'VERSIONE',CRS:'EPSG:3003','DPI':150}
      })
    })



    class toolbar extends ol.control.Control {

        constructor(opt_options) {
          const options = opt_options || {main:true};

          const toolbar = document.createElement('div');
          toolbar.className = 'bar';

          let strong = document.createElement('strong');
          strong.className = 'etic';
          strong.innerHTML = 'MULTI GEOMETRIA ';
          toolbar.appendChild(strong);
      
          const button1 = document.createElement('button');
          button1.className = 'btn';
          button1.innerHTML = '<';
          let span = document.createElement('span');
          span.className = 'tool';
          span.appendChild(button1);
          toolbar.appendChild(span);
      
          const button2 = document.createElement('button');
          button2.className = 'btn';
          button2.innerHTML = '>';
          span = document.createElement('span');
          span.className = '';
          span.appendChild(button2);

          toolbar.appendChild(span);
      
          const element = document.createElement('div');
          element.className = 'toolbar btn-toolbar ol-unselectable ol-control';
          element.appendChild(toolbar);
      
          super({
            element: element,
            target: options.target,
          });

          this.button = button1
          button1.addEventListener('click', this.handleclick.bind(this), false);
          this.button = button2
          button2.addEventListener('click', this.handleclick.bind(this), false);

          this.element = element
        }

        handleclick(evt) {
            console.log("handleclick",this)
            if (this.button.innerHTML == "<") {
                currentID -= 1
                if (currentID < 0) {
                    currentID = multiID
                }
            } else {
                currentID += 1
                if (currentID > multiID) {
                    currentID = 0
                }
            }
            polyOverlaysx.getSource().refresh()
            polyOverlaydx.getSource().refresh()
            let extent = multipolygon.getExtent();
            if (currentID != multiID) {
                extent = multipolygon.getPolygon(currentID).getExtent();
            }
            map_glob.getView().fit(extent, map_glob.getSize());
            evt.preventDefault();
        }
      }



      class comboversioni extends ol.control.Control {
  
          constructor(versioni,idx_corrente,target_position,opts) {
  
            const options = opts || {main:true};
            //const combo = document.createElement('div');
  
            let select = document.createElement('select');
            select.className = 'form-select';
            //select.innerHTML = 'MULTI GEOMETRIA ';
            //combo.appendChild(select);

            versioni.forEach((element) => {
                const opt = document.createElement('option');
                //opt.className = 'btn';
                opt.value = element.wms
                opt.innerHTML = element.nome;
                select.appendChild(opt);
            });
      
            select.value = versioni[idx_corrente].wms;

            const element = document.createElement('div');
            element.className = 'ol-unselectable ol-control combov'+target_position;
            element.appendChild(select);
        
            super({
              element: element,
              target: options.target,
            });
  
            this.select = select
            select.addEventListener('change', this.handlechange.bind(this), false);
  
            this.element = element
          }
  
          handlechange(evt) {
              //let combo = this.getElementsByClassName('form-select')
              console.log("handlechange wms",this.select.value)
              console.log("handlechange this",this)
              console.log("handlechange evt",evt)
              let target
              if (this.element.classList.contains('combovSX')) {
                target = currentOverlay
              } else {
                target = versionOverlay
              }

              target.getSource().setUrl(this.select.value)
              target.getSource().refresh()
              //polyOverlaysx.getSource().refresh()
              //polyOverlaydx.getSource().refresh()
              //map_glob.getView().fit(extent, map_glob.getSize());
              //evt.preventDefault();
          }
        }

    map_glob = new ol.Map({
        layers: [currentOverlay, dbtOverlaySx, polyOverlaysx, versionOverlay, dbtOverlayDx ,polyOverlaydx ],
        controls: ol.control.defaults({
            attribution: false
          }).extend([
            //new ol.control.ScaleLine(),
            new ol.control.MousePosition(),
        ]),
        target: 'map',
        view: new ol.View({
            projection: targetProjection,
            center: ol.extent.getCenter(targetExtent),
            zoom: 2
        })
    });

    if (currentID != 99999) {
        map_glob.addControl(new toolbar());
    }

    var layerSwitcher = new ol.control.LayerSwitcher({
        tipLabel: 'Legenda' // Optional label for button
    });

        // Control
    var ctrl = new ol.control.Swipe({"position":slider});
    map_glob.addControl(ctrl);

    // CurrentOverlaySX control

    var currentOverlaySX_control = new comboversioni(versioni_wms,1,"SX")
    if (base_wms == "") {
        currentOverlaySX_control = new comboversioni([versioni_wms[1]],0,"SX")
    } 
    map_glob.addControl(currentOverlaySX_control);
    var currentOverlayDX_control = new comboversioni(versioni_wms,0,"DX")
    map_glob.addControl(currentOverlayDX_control);

    // Set stamen on left
    ctrl.addLayer(currentOverlay);
    ctrl.addLayer(dbtOverlaySx);
    ctrl.addLayer(polyOverlaysx);
    // OSM on right
    ctrl.addLayer(versionOverlay, true);
    ctrl.addLayer(dbtOverlayDx, true);
    ctrl.addLayer(polyOverlaydx, true);

    map_glob.getView().on('propertychange', function(e) {
        switch (e.key) {
            case 'resolution':
            console.log('resolution');
            console.log(e.oldValue);
            break;
        }
    });

    map_glob.addControl(layerSwitcher);

    extent = polyOverlaysx.getSource().getExtent();
    map_glob.getView().fit(extent, map_glob.getSize());
    
    //enable_layer_state_tracking(map_glob)
}