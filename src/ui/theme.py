"""Central design token registry. Import from here, never hardcode values."""

# Background levels
BG_BASE    = (0.08, 0.10, 0.12, 1)   # screen background
BG_SURFACE = (0.13, 0.16, 0.20, 1)   # cards, panels
BG_RAISED  = (0.17, 0.21, 0.26, 1)   # elevated elements, header
BG_INPUT   = (0.12, 0.15, 0.19, 1)   # text inputs

# Accent colours
C_GREEN    = (0.20, 0.85, 0.55, 1)   # primary action, own chat bubble
C_MASTER   = (0.95, 0.60, 0.10, 1)   # amber — master role
C_NODE     = (0.15, 0.65, 0.85, 1)   # sky blue — node role
C_DANGER   = (0.80, 0.25, 0.20, 1)   # stop, error
C_SUCCESS  = (0.20, 0.70, 0.45, 1)   # connected, ok
C_WARNING  = (0.90, 0.70, 0.10, 1)   # pending

# Text
T_PRIMARY  = (0.95, 0.95, 0.95, 1)
T_SECONDARY= (0.65, 0.68, 0.72, 1)
T_DIM      = (0.40, 0.42, 0.46, 1)
T_LINK     = C_NODE

# Spacing (use as dp values for size_hint_y=None, height=SPACE_*)
SPACE_XS   = 4
SPACE_SM   = 8
SPACE_MD   = 16
SPACE_LG   = 24
SPACE_XL   = 32

# Radii
RADIUS_SM  = [6]
RADIUS_MD  = [10]
RADIUS_LG  = [16]

# Font sizes (sp strings)
FS_XS  = "11sp"
FS_SM  = "13sp"
FS_MD  = "15sp"
FS_LG  = "18sp"
FS_XL  = "22sp"
FS_XXL = "32sp"

# Common heights
H_HEADER = 56
H_BTN    = 52
H_BTN_SM = 42
H_INPUT  = 46
H_ROW    = 68
H_NAV    = 58
