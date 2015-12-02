var geocoder;
var map;
var lookupUnknownIter;
var toCacheLocations = []
var currentWindow = null;

var provideLocations = function(action) {
    provideLocations_Local(jQuery, action);
}

var provideLocations_Local = function($, action)
{
    var form = $('<form method="POST" action="'+action+'" id="geocodeForm"></form>');
    for(var i=0;i<locations.length;i++) {
        form.append('<input type="hidden" name="addresses-'+i+'.row" value="'+locations[i][0]+'" />')
        form.append('<input type="hidden" name="addresses-'+i+'.address" value="'+locations[i][1]+'" />');
    }
    form.appendTo(window.frames['remoter'].document.body);
    window.frames['remoter'].document.forms['geocodeForm'].submit();
}

var loadMap = function(known, unknown, apiKey) {
    loadMap_Local(jQuery, known, unknown, apiKey);
}

var loadMap_Local = function($, known, unknown, apiKey) {
    var script = document.createElement('script');
    // should namespace these at the moment
    knownLocations = known;
    unknownLocations = unknown;

    $('#tablemap').before('<script type="text/javascript" src="http://maps.googleapis.com/maps/api/js?key='+apiKey+'&sensor=false&callback=initializeMap"></script>')
}

var initializeMap = function() {
    geocoder = new google.maps.Geocoder();
    lookupUnknownIter = lookupUnknownAddresses(0);
    lookupUnknownIter(drawMap)
}

var lookupUnknownAddresses = function(index) {
    var callback = function(last_cb) {
        if(index >= unknownLocations.length) {
            last_cb();
            return;
        }
        // should namespace this
        lookupUnknownIter = lookupUnknownAddresses(index+1);
        geocoder.geocode({'address': unknownLocations[index][1]}, function(results, status) {
            if(status == google.maps.GeocoderStatus.OK) {
                var loc = results[0].geometry.location;
                toCacheLocations.push([unknownLocations[index][0], unknownLocations[index][1], true, loc.lat(), loc.lng()]);
            }
            else if(status == google.maps.GeocoderStatus.ZERO_RESULTS) {
                toCacheLocations.push([unknownLocations[index][0], unknownLocations[index][1], false]);
            }
            else {
                alert("Could not look up address: "+unknownLocations[index][1])
            }
            lookupUnknownIter(last_cb);
        });
    }
    return callback;
}

var drawMap = function() {
    drawMap_Local(jQuery);
}

var drawMap_Local = function($)
{
    var bounds = new google.maps.LatLngBounds();
    for(var i=0;i<toCacheLocations.length;i++) {
        if(toCacheLocations[i][2]) {
            var latlng = new google.maps.LatLng(toCacheLocations[i][3],
                                            toCacheLocations[i][4]);
            bounds.extend(latlng);
        }
    }
    for(var i=0;i<knownLocations.length;i++) {
        var latlng = new google.maps.LatLng(knownLocations[i][2],
                                            knownLocations[i][3]);
        bounds.extend(latlng);
    }
    $('#tablemap').css({width: '100%', height: '600px', marginBottom: '1em'});
    var mapOptions = {
        center: bounds.getCenter(),
        zoom: 8,
        mapTypeId: google.maps.MapTypeId.ROADMAP
    };
    map = new google.maps.Map(document.getElementById('tablemap'), mapOptions);
    map.fitBounds(bounds);

    var infoRows = $('#tablemap + div > table');
    for(var i=0;i<toCacheLocations.length;i++) {
        var row = $(infoRows).find('tr:eq('+toCacheLocations[i][0]+')');
        var latlng = new google.maps.LatLng(toCacheLocations[i][3],
                                            toCacheLocations[i][4]);
        createMarker(latlng, row.children('td:eq('+customerColumn+')').text(),
                             row.children('td:eq('+locationColumn+')').text())
    }
    for(var i=0;i<knownLocations.length;i++) {
        var row = $(infoRows).find('tr:eq('+knownLocations[i][0]+')');
        var latlng = new google.maps.LatLng(knownLocations[i][2],
                                            knownLocations[i][3]);
        createMarker(latlng, row.children('td:eq('+customerColumn+')').text(),
                             row.children('td:eq('+locationColumn+')').text())
    }
    if(toCacheLocations.length > 0) {
        cacheLocations($);
    }
}

var createMarker = function(pos, customer, location) {
    var marker = new google.maps.Marker({
        position: pos,
        map: map,
        title: customer
    });
    var infoWindow = new google.maps.InfoWindow({
        content: '<h2>'+customer+'</h2><p>'+location+'</p>'
    });
    google.maps.event.addListener(marker, 'click', function() {
        if(currentWindow != null) {
            currentWindow.close();
        }
        currentWindow = new google.maps.InfoWindow({
            content: '<h4>'+customer+'</h4>'
        })
        currentWindow.open(map, marker);
    })
    google.maps.event.addListener(marker, 'dblclick', function() {
        map.setZoom(8);
        map.setCenter(marker.getPosition());
    })
}

var cacheLocations = function($)
{
    var form = $('<form method="POST" action="${url(controller='map', action='cache')}" id="cacheForm"></form>');
    for(var i=0;i<toCacheLocations.length;i++) {
        form.append('<input type="hidden" name="addresses-'+i+'.address" value="'+toCacheLocations[i][1]+'" />')
        form.append('<input type="hidden" name="addresses-'+i+'.validated" value="'+toCacheLocations[i][2]+'" />')
        if(toCacheLocations[i][2]) {
            form.append('<input type="hidden" name="addresses-'+i+'.lat" value="'+toCacheLocations[i][3]+'" />')
            form.append('<input type="hidden" name="addresses-'+i+'.lon" value="'+toCacheLocations[i][4]+'" />');
        }
    }
    form.appendTo(window.frames['remoter'].document.body);
    window.frames['remoter'].document.forms['cacheForm'].submit();
}

jQuery(function($)
{
    document.domain = "${c.origin}";
    $(function() {
        $('#tablemap').before('<iframe name="remoter" style="width: 0px; height: 0px; visibility: hidden;" id="remoter" src="${c.protocol}://${c.server_root}${url(controller='map', action='iframe')}"></iframe>');

    });
});