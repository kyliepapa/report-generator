"""Resolve CompanyCam display and original image URLs from photo payloads."""


def resolve_image_urls(photo):
    """
    Return (display_url, original_url) from a CompanyCam photo dict.

    display_url prefers the web-sized URI for embedding; original_url
    prefers the full-resolution URI for download links.
    """
    uris = photo.get("uris", []) if isinstance(photo, dict) else []
    web_url = original_url = fallback = None

    if isinstance(uris, list):
        for u in uris:
            if not isinstance(u, dict):
                continue
            uurl = u.get("url")
            if not uurl:
                continue
            utype = u.get("type")
            if utype == "web":
                web_url = uurl
            elif utype == "original":
                original_url = uurl
            elif fallback is None:
                fallback = uurl

    display = web_url or original_url or fallback
    original = original_url or web_url or fallback
    return display, original
