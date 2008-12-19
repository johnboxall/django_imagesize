__test__ = {"imagesize":"""
>>> from imagesize.helpers import _get_image_size, get_image_size, process

# Test _get_image_size on all types of images (jpg/png/gif)
>>> _get_image_size("http://www.python.org/images/success/nasa.jpg")
(240, 90)
>>> _get_image_size("http://python.org./images/sun_logo.png")
(170, 85)
>>> _get_image_size("http://python.org./images/PythonPowered.gif")
(110, 44)

# Test get_image_size

# Get three images - they should return none for size cause they don't exist.
>>> get_image_size("http://www.python.org/images/success/nasa.jpg")
>>> get_image_size("http://python.org./images/sun_logo.png")
>>> get_image_size("http://python.org./images/PythonPowered.gif")

# Process the three images.
>>> process()
3

# Now get the sizes again!
>>> get_image_size("http://www.python.org/images/success/nasa.jpg")
(240L, 90L)
>>> get_image_size("http://python.org./images/sun_logo.png")
(170L, 85L)
>>> get_image_size("http://python.org./images/PythonPowered.gif")
(110L, 44L)

"""}