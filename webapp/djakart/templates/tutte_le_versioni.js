var current_version_name = "{{ current_version.nome }}";
var current_version_id = "{{ current_version.pk }}";
var targetExtent = {{ current_version.extent }};
var versioni_wms = JSON.parse('{{vlist|escapejs}}');