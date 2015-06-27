
requirejs([
    "http://code.jquery.com/jquery-1.10.1.min.js",
    "http://cdn.leafletjs.com/leaflet-0.7.2/leaflet.js"
], function(jQuery, L) {

    var layer = L.tileLayer('http://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
    });


    var icon = L.icon({
        iconUrl: '/static/images/pyvo-marker.png',
        iconSize: [50, 50],
        shadowSize: [0, 0],
        iconAnchor: [25, 50],
        popupAnchor: [0, -50]
    });


    $(function() {
        var element = $('#map');

        var zoom = element.attr('data-zoom') || 11;
        var lat = element.attr('data-lat') || 49.8;
        var lng = element.attr('data-lng') || 15.55;

        var map = L.map('map')
            .setView([lat, lng], zoom)
            .addLayer(layer);

        var dataUrl = element.attr('data-src');
        $.getJSON(dataUrl, function(data) {
            L.geoJson(data, {
                pointToLayer: function (feature, coordinates) {
                    return L.marker(coordinates, {icon: icon});
                },
                onEachFeature: function (feature, marker) {
                    if (feature.properties) {
                        text = '<h3>' + feature.properties.name + '</h3><p>' + feature.properties.address + '</p>' +
                            '<a class="maplink" href="http://mapy.cz/zakladni?q=' + feature.properties.name + ', ' + feature.geometry.coordinates[1] + 'N+' + feature.geometry.coordinates[0] + 'E ">→mapy.cz</a>';
                        marker.bindPopup(text);
                    }
                }
            }).addTo(map);
        });
    });

});
