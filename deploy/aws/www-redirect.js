// CloudFront Function (cloudfront-js-2.0, viewer-request): www.<alan> → https://<alan> (301).
// Yol ve sorgu dizesi korunur; www olmayan istekler dokunulmadan geçer. Alan adı koda
// gömülü değil: "www." öneki atılır.
function handler(event) {
  var request = event.request;
  var host = request.headers.host ? request.headers.host.value : "";
  if (host.indexOf("www.") !== 0) {
    return request;
  }
  var parts = [];
  var qs = request.querystring;
  for (var key in qs) {
    var values = qs[key].multiValue ? qs[key].multiValue : [qs[key]];
    for (var i = 0; i < values.length; i++) {
      parts.push(values[i].value === "" ? key : key + "=" + values[i].value);
    }
  }
  var location = "https://" + host.substring(4) + request.uri + (parts.length ? "?" + parts.join("&") : "");
  return {
    statusCode: 301,
    statusDescription: "Moved Permanently",
    headers: {
      location: { value: location },
      "cache-control": { value: "max-age=3600" }
    }
  };
}
