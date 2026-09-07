"""Shared paths and native resource-family names for the dual-weapon tools."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CLIENT = Path(os.environ.get('RO_DUAL_CLIENT', 'D:/Programs/Games/Ragnarok/02_client/Banquet of Heroes'))
EXE = CLIENT / '2025-07-16_Ragexe_175220998_clientinfo_patched.exe'
FAMILIES = {'assassin': 'data/sprite/인간족/어세신/어세신_남_',
            'shadow_cross': 'data/sprite/인간족/shadow_cross/shadow_cross_남_'}
BODIES = {'assassin': ('어세신_남', 'assassin'),
          'assassin_high': ('어세신_h_남', 'assassin'),
          'assassin_cross': ('어쌔신크로스_남', 'assassin'),
          'guillotine_cross': ('길로틴크로스_남', 'assassin'),
          'shadow_cross': ('shadow_cross_남', 'shadow_cross')}
INPUT=ROOT/'Inputs/DualWeaponAuthored/grips/female-assassin-pixel-landmarks.json'
BODY='data/sprite/인간족/몸통/여/어쌔신크로스_여'
