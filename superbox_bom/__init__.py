"""ABB ReliaGear neXT SuperBox BOM generator.

Turns a panel spec (main type + breaker loadout + enclosure) into an
orderable bill of materials for a merchandised ReliaGear neXT SuperBox,
or refuses with a "factory-assembled required" flag when the config falls
outside the merchandised envelope.

Source of truth: ABB BuyLog Section 11 (see ABBPDF.pdf / data/*.json).
"""

__version__ = "0.1.0"
