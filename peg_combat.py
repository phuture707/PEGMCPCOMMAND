#!/usr/bin/env python3
"""
Pegasus Galaxy Combat Simulator & Battle Calculator Engine
Simulates space battles with exact game mechanics:
- Initiative-based firing order (PDS -> Strike Crafts -> Warships)
- Class targeting prioritization (LIGHT, MEDIUM, HEAVY, RESOURCES, ROIDS)
- Planetary Shield Generator damage absorption
- EMP disabling mechanics
- Hulls and PDS research multipliers
- Resource cargo & plunder projections
"""

import json
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# --- Official Ship Combat Definitions (from pegasus://ship/definitions) ---
SHIP_DEFINITIONS: Dict[str, Dict[str, Any]] = {   'main-ashkari-claw-extractor': {   'armor': 200,
                                       'asteroidCapacity': 5,
                                       'capitalAbility': None,
                                       'category': 'FRIGATE',
                                       'cloak': False,
                                       'cost': {   'crystal': 6000,
                                                   'eonium': 4000,
                                                   'metal': 10000},
                                       'damage': 0,
                                       'empDamage': 0,
                                       'empResistance': 10,
                                       'faction': 'ASHKARI',
                                       'gun': 0,
                                       'id': 'main-ashkari-claw-extractor',
                                       'init': 12,
                                       'name': 'Claw Extractor',
                                       'resourceCapacity': 0,
                                       'shipClass': 'MEDIUM',
                                       'targetClass1': 'ROIDS',
                                       'targetClass2': '',
                                       'targetClass3': ''},
    'main-ashkari-fang': {   'armor': 20,
                             'asteroidCapacity': 0,
                             'capitalAbility': None,
                             'category': 'FIGHTER',
                             'cloak': False,
                             'cost': {   'crystal': 500,
                                         'eonium': 500,
                                         'metal': 900},
                             'damage': 16,
                             'empDamage': 0,
                             'empResistance': 0,
                             'faction': 'ASHKARI',
                             'gun': 8,
                             'id': 'main-ashkari-fang',
                             'init': 3,
                             'name': 'Fang',
                             'resourceCapacity': 0,
                             'shipClass': 'LIGHT',
                             'targetClass1': 'MEDIUM',
                             'targetClass2': 'LIGHT',
                             'targetClass3': 'HEAVY'},
    'main-ashkari-marauder': {   'armor': 66,
                                 'asteroidCapacity': 0,
                                 'capitalAbility': None,
                                 'category': 'DESTROYER',
                                 'cloak': False,
                                 'cost': {   'crystal': 2400,
                                             'eonium': 2400,
                                             'metal': 4200},
                                 'damage': 54,
                                 'empDamage': 0,
                                 'empResistance': 0,
                                 'faction': 'ASHKARI',
                                 'gun': 17,
                                 'id': 'main-ashkari-marauder',
                                 'init': 5,
                                 'name': 'Marauder',
                                 'resourceCapacity': 0,
                                 'shipClass': 'MEDIUM',
                                 'targetClass1': 'LIGHT',
                                 'targetClass2': 'MEDIUM',
                                 'targetClass3': 'HEAVY'},
    'main-ashkari-oblivion': {   'armor': 470,
                                 'asteroidCapacity': 0,
                                 'capitalAbility': {   'damageReflectPercent': 15,
                                                       'type': 'siege_barrier'},
                                 'category': 'BATTLESHIP',
                                 'cloak': False,
                                 'cost': {   'crystal': 18000,
                                             'eonium': 19000,
                                             'metal': 30000},
                                 'damage': 250,
                                 'empDamage': 0,
                                 'empResistance': 100,
                                 'faction': 'ASHKARI',
                                 'gun': 55,
                                 'id': 'main-ashkari-oblivion',
                                 'init': 7,
                                 'name': 'Oblivion',
                                 'resourceCapacity': 0,
                                 'shipClass': 'SPECIAL',
                                 'targetClass1': 'HEAVY',
                                 'targetClass2': 'MEDIUM',
                                 'targetClass3': 'LIGHT'},
    'main-ashkari-plunder-barge': {   'armor': 150,
                                      'asteroidCapacity': 0,
                                      'capitalAbility': None,
                                      'category': 'FRIGATE',
                                      'cloak': False,
                                      'cost': {   'crystal': 4000,
                                                  'eonium': 2500,
                                                  'metal': 8000},
                                      'damage': 0,
                                      'empDamage': 0,
                                      'empResistance': 10,
                                      'faction': 'ASHKARI',
                                      'gun': 0,
                                      'id': 'main-ashkari-plunder-barge',
                                      'init': 12,
                                      'name': 'Plunder Barge',
                                      'resourceCapacity': 50000,
                                      'shipClass': 'MEDIUM',
                                      'targetClass1': 'RESOURCES',
                                      'targetClass2': '',
                                      'targetClass3': ''},
    'main-ashkari-raid-runner': {   'armor': 80,
                                    'asteroidCapacity': 0,
                                    'capitalAbility': None,
                                    'category': 'CORVETTE',
                                    'cloak': False,
                                    'cost': {   'crystal': 2500,
                                                'eonium': 1500,
                                                'metal': 5000},
                                    'damage': 0,
                                    'empDamage': 0,
                                    'empResistance': 5,
                                    'faction': 'ASHKARI',
                                    'gun': 0,
                                    'id': 'main-ashkari-raid-runner',
                                    'init': 12,
                                    'name': 'Raid Runner',
                                    'resourceCapacity': 25000,
                                    'shipClass': 'LIGHT',
                                    'targetClass1': 'RESOURCES',
                                    'targetClass2': '',
                                    'targetClass3': ''},
    'main-ashkari-ravager': {   'armor': 54,
                                'asteroidCapacity': 0,
                                'capitalAbility': None,
                                'category': 'FRIGATE',
                                'cloak': False,
                                'cost': {   'crystal': 1800,
                                            'eonium': 1800,
                                            'metal': 3200},
                                'damage': 44,
                                'empDamage': 0,
                                'empResistance': 0,
                                'faction': 'ASHKARI',
                                'gun': 15,
                                'id': 'main-ashkari-ravager',
                                'init': 4,
                                'name': 'Ravager',
                                'resourceCapacity': 0,
                                'shipClass': 'MEDIUM',
                                'targetClass1': 'MEDIUM',
                                'targetClass2': 'LIGHT',
                                'targetClass3': 'HEAVY'},
    'main-ashkari-reaper': {   'armor': 80,
                               'asteroidCapacity': 0,
                               'capitalAbility': None,
                               'category': 'DESTROYER',
                               'cloak': False,
                               'cost': {   'crystal': 3000,
                                           'eonium': 3000,
                                           'metal': 5200},
                               'damage': 62,
                               'empDamage': 0,
                               'empResistance': 0,
                               'faction': 'ASHKARI',
                               'gun': 19,
                               'id': 'main-ashkari-reaper',
                               'init': 5,
                               'name': 'Reaper',
                               'resourceCapacity': 0,
                               'shipClass': 'MEDIUM',
                               'targetClass1': 'MEDIUM',
                               'targetClass2': 'HEAVY',
                               'targetClass3': 'LIGHT'},
    'main-ashkari-talon': {   'armor': 26,
                              'asteroidCapacity': 0,
                              'capitalAbility': None,
                              'category': 'FIGHTER',
                              'cloak': False,
                              'cost': {   'crystal': 700,
                                          'eonium': 700,
                                          'metal': 1250},
                              'damage': 21,
                              'empDamage': 0,
                              'empResistance': 0,
                              'faction': 'ASHKARI',
                              'gun': 10,
                              'id': 'main-ashkari-talon',
                              'init': 3,
                              'name': 'Talon',
                              'resourceCapacity': 0,
                              'shipClass': 'LIGHT',
                              'targetClass1': 'LIGHT',
                              'targetClass2': 'MEDIUM',
                              'targetClass3': 'HEAVY'},
    'main-ashkari-viper': {   'armor': 30,
                              'asteroidCapacity': 0,
                              'capitalAbility': None,
                              'category': 'FIGHTER',
                              'cloak': False,
                              'cost': {   'crystal': 850,
                                          'eonium': 850,
                                          'metal': 1500},
                              'damage': 24,
                              'empDamage': 0,
                              'empResistance': 0,
                              'faction': 'ASHKARI',
                              'gun': 11,
                              'id': 'main-ashkari-viper',
                              'init': 4,
                              'name': 'Viper',
                              'resourceCapacity': 0,
                              'shipClass': 'LIGHT',
                              'targetClass1': 'MEDIUM',
                              'targetClass2': 'HEAVY',
                              'targetClass3': 'LIGHT'},
    'main-synthara-arc': {   'armor': 46,
                             'asteroidCapacity': 0,
                             'capitalAbility': None,
                             'category': 'FIGHTER',
                             'cloak': False,
                             'cost': {   'crystal': 1200,
                                         'eonium': 500,
                                         'metal': 1100},
                             'damage': 0,
                             'empDamage': 14,
                             'empResistance': 14,
                             'faction': 'SYNTHARA',
                             'gun': 7,
                             'id': 'main-synthara-arc',
                             'init': 5,
                             'name': 'Arc',
                             'resourceCapacity': 0,
                             'shipClass': 'LIGHT',
                             'targetClass1': 'LIGHT',
                             'targetClass2': 'HEAVY',
                             'targetClass3': 'MEDIUM'},
    'main-synthara-crystal-borer': {   'armor': 280,
                                       'asteroidCapacity': 10,
                                       'capitalAbility': None,
                                       'category': 'CRUISER',
                                       'cloak': False,
                                       'cost': {   'crystal': 9000,
                                                   'eonium': 6000,
                                                   'metal': 15000},
                                       'damage': 0,
                                       'empDamage': 0,
                                       'empResistance': 15,
                                       'faction': 'SYNTHARA',
                                       'gun': 0,
                                       'id': 'main-synthara-crystal-borer',
                                       'init': 12,
                                       'name': 'Crystal Borer',
                                       'resourceCapacity': 0,
                                       'shipClass': 'HEAVY',
                                       'targetClass1': 'ROIDS',
                                       'targetClass2': '',
                                       'targetClass3': ''},
    'main-synthara-monolith': {   'armor': 250,
                                  'asteroidCapacity': 0,
                                  'capitalAbility': None,
                                  'category': 'CRUISER',
                                  'cloak': False,
                                  'cost': {   'crystal': 8000,
                                              'eonium': 3500,
                                              'metal': 7500},
                                  'damage': 0,
                                  'empDamage': 30,
                                  'empResistance': 40,
                                  'faction': 'SYNTHARA',
                                  'gun': 20,
                                  'id': 'main-synthara-monolith',
                                  'init': 8,
                                  'name': 'Monolith',
                                  'resourceCapacity': 0,
                                  'shipClass': 'HEAVY',
                                  'targetClass1': 'HEAVY',
                                  'targetClass2': 'MEDIUM',
                                  'targetClass3': 'LIGHT'},
    'main-synthara-nexus': {   'armor': 54,
                               'asteroidCapacity': 0,
                               'capitalAbility': None,
                               'category': 'FIGHTER',
                               'cloak': False,
                               'cost': {   'crystal': 1450,
                                           'eonium': 600,
                                           'metal': 1300},
                               'damage': 0,
                               'empDamage': 16,
                               'empResistance': 16,
                               'faction': 'SYNTHARA',
                               'gun': 8,
                               'id': 'main-synthara-nexus',
                               'init': 6,
                               'name': 'Nexus',
                               'resourceCapacity': 0,
                               'shipClass': 'LIGHT',
                               'targetClass1': 'HEAVY',
                               'targetClass2': 'MEDIUM',
                               'targetClass3': 'LIGHT'},
    'main-synthara-nexus-freighter': {   'armor': 220,
                                         'asteroidCapacity': 0,
                                         'capitalAbility': None,
                                         'category': 'CRUISER',
                                         'cloak': False,
                                         'cost': {   'crystal': 6000,
                                                     'eonium': 4000,
                                                     'metal': 12000},
                                         'damage': 0,
                                         'empDamage': 0,
                                         'empResistance': 15,
                                         'faction': 'SYNTHARA',
                                         'gun': 0,
                                         'id': 'main-synthara-nexus-freighter',
                                         'init': 12,
                                         'name': 'Nexus Freighter',
                                         'resourceCapacity': 100000,
                                         'shipClass': 'HEAVY',
                                         'targetClass1': 'RESOURCES',
                                         'targetClass2': '',
                                         'targetClass3': ''},
    'main-synthara-obelisk': {   'armor': 330,
                                 'asteroidCapacity': 0,
                                 'capitalAbility': None,
                                 'category': 'BATTLESHIP',
                                 'cloak': False,
                                 'cost': {   'crystal': 11000,
                                             'eonium': 5500,
                                             'metal': 10500},
                                 'damage': 0,
                                 'empDamage': 36,
                                 'empResistance': 50,
                                 'faction': 'SYNTHARA',
                                 'gun': 24,
                                 'id': 'main-synthara-obelisk',
                                 'init': 9,
                                 'name': 'Obelisk',
                                 'resourceCapacity': 0,
                                 'shipClass': 'HEAVY',
                                 'targetClass1': 'MEDIUM',
                                 'targetClass2': 'HEAVY',
                                 'targetClass3': 'LIGHT'},
    'main-synthara-oracle': {   'armor': 640,
                                'asteroidCapacity': 0,
                                'capitalAbility': {   'fleetEmpChanceMultiplier': 0.3,
                                                      'type': 'disruption_field'},
                                'category': 'BATTLESHIP',
                                'cloak': True,
                                'cost': {   'crystal': 29000,
                                            'eonium': 12000,
                                            'metal': 24000},
                                'damage': 0,
                                'empDamage': 60,
                                'empResistance': 80,
                                'faction': 'SYNTHARA',
                                'gun': 30,
                                'id': 'main-synthara-oracle',
                                'init': 8,
                                'name': 'Oracle',
                                'resourceCapacity': 0,
                                'shipClass': 'SPECIAL',
                                'targetClass1': 'HEAVY',
                                'targetClass2': 'MEDIUM',
                                'targetClass3': 'LIGHT'},
    'main-synthara-pulse': {   'armor': 40,
                               'asteroidCapacity': 0,
                               'capitalAbility': None,
                               'category': 'FIGHTER',
                               'cloak': False,
                               'cost': {   'crystal': 1000,
                                           'eonium': 400,
                                           'metal': 900},
                               'damage': 0,
                               'empDamage': 12,
                               'empResistance': 12,
                               'faction': 'SYNTHARA',
                               'gun': 6,
                               'id': 'main-synthara-pulse',
                               'init': 5,
                               'name': 'Pulse',
                               'resourceCapacity': 0,
                               'shipClass': 'LIGHT',
                               'targetClass1': 'HEAVY',
                               'targetClass2': 'LIGHT',
                               'targetClass3': 'MEDIUM'},
    'main-synthara-pulse-courier': {   'armor': 80,
                                       'asteroidCapacity': 0,
                                       'capitalAbility': None,
                                       'category': 'CORVETTE',
                                       'cloak': False,
                                       'cost': {   'crystal': 2500,
                                                   'eonium': 1500,
                                                   'metal': 5000},
                                       'damage': 0,
                                       'empDamage': 0,
                                       'empResistance': 5,
                                       'faction': 'SYNTHARA',
                                       'gun': 0,
                                       'id': 'main-synthara-pulse-courier',
                                       'init': 12,
                                       'name': 'Pulse Courier',
                                       'resourceCapacity': 25000,
                                       'shipClass': 'LIGHT',
                                       'targetClass1': 'RESOURCES',
                                       'targetClass2': '',
                                       'targetClass3': ''},
    'main-synthara-singularity': {   'armor': 420,
                                     'asteroidCapacity': 0,
                                     'capitalAbility': None,
                                     'category': 'BATTLESHIP',
                                     'cloak': False,
                                     'cost': {   'crystal': 14000,
                                                 'eonium': 7500,
                                                 'metal': 13000},
                                     'damage': 0,
                                     'empDamage': 42,
                                     'empResistance': 60,
                                     'faction': 'SYNTHARA',
                                     'gun': 28,
                                     'id': 'main-synthara-singularity',
                                     'init': 9,
                                     'name': 'Singularity',
                                     'resourceCapacity': 0,
                                     'shipClass': 'HEAVY',
                                     'targetClass1': 'HEAVY',
                                     'targetClass2': 'MEDIUM',
                                     'targetClass3': 'LIGHT'},
    'main-synthara-singularity-hauler': {   'armor': 400,
                                            'asteroidCapacity': 0,
                                            'capitalAbility': None,
                                            'category': 'CRUISER',
                                            'cloak': False,
                                            'cost': {   'crystal': 12000,
                                                        'eonium': 8000,
                                                        'metal': 20000},
                                            'damage': 0,
                                            'empDamage': 0,
                                            'empResistance': 20,
                                            'faction': 'SYNTHARA',
                                            'gun': 0,
                                            'id': 'main-synthara-singularity-hauler',
                                            'init': 12,
                                            'name': 'Singularity Hauler',
                                            'resourceCapacity': 200000,
                                            'shipClass': 'HEAVY',
                                            'targetClass1': 'RESOURCES',
                                            'targetClass2': '',
                                            'targetClass3': ''},
    'main-synthara-void-harvester': {   'armor': 380,
                                        'asteroidCapacity': 18,
                                        'capitalAbility': None,
                                        'category': 'CRUISER',
                                        'cloak': False,
                                        'cost': {   'crystal': 13000,
                                                    'eonium': 9000,
                                                    'metal': 22000},
                                        'damage': 0,
                                        'empDamage': 0,
                                        'empResistance': 20,
                                        'faction': 'SYNTHARA',
                                        'gun': 0,
                                        'id': 'main-synthara-void-harvester',
                                        'init': 12,
                                        'name': 'Void Harvester',
                                        'resourceCapacity': 0,
                                        'shipClass': 'HEAVY',
                                        'targetClass1': 'ROIDS',
                                        'targetClass2': '',
                                        'targetClass3': ''},
    'main-vanguard-centurion': {   'armor': 74,
                                   'asteroidCapacity': 0,
                                   'capitalAbility': None,
                                   'category': 'FRIGATE',
                                   'cloak': False,
                                   'cost': {   'crystal': 1400,
                                               'eonium': 900,
                                               'metal': 2200},
                                   'damage': 44,
                                   'empDamage': 0,
                                   'empResistance': 10,
                                   'faction': 'VANGUARD',
                                   'gun': 15,
                                   'id': 'main-vanguard-centurion',
                                   'init': 4,
                                   'name': 'Centurion',
                                   'resourceCapacity': 0,
                                   'shipClass': 'MEDIUM',
                                   'targetClass1': 'MEDIUM',
                                   'targetClass2': 'HEAVY',
                                   'targetClass3': 'LIGHT'},
    'main-vanguard-colossus': {   'armor': 340,
                                  'asteroidCapacity': 0,
                                  'capitalAbility': None,
                                  'category': 'BATTLESHIP',
                                  'cloak': False,
                                  'cost': {   'crystal': 7600,
                                              'eonium': 5400,
                                              'metal': 11200},
                                  'damage': 156,
                                  'empDamage': 0,
                                  'empResistance': 30,
                                  'faction': 'VANGUARD',
                                  'gun': 30,
                                  'id': 'main-vanguard-colossus',
                                  'init': 6,
                                  'name': 'Colossus',
                                  'resourceCapacity': 0,
                                  'shipClass': 'HEAVY',
                                  'targetClass1': 'HEAVY',
                                  'targetClass2': 'MEDIUM',
                                  'targetClass3': 'LIGHT'},
    'main-vanguard-core-driller': {   'armor': 280,
                                      'asteroidCapacity': 10,
                                      'capitalAbility': None,
                                      'category': 'CRUISER',
                                      'cloak': False,
                                      'cost': {   'crystal': 9000,
                                                  'eonium': 6000,
                                                  'metal': 15000},
                                      'damage': 0,
                                      'empDamage': 0,
                                      'empResistance': 15,
                                      'faction': 'VANGUARD',
                                      'gun': 0,
                                      'id': 'main-vanguard-core-driller',
                                      'init': 12,
                                      'name': 'Core Driller',
                                      'resourceCapacity': 0,
                                      'shipClass': 'HEAVY',
                                      'targetClass1': 'ROIDS',
                                      'targetClass2': '',
                                      'targetClass3': ''},
    'main-vanguard-fortress-transport': {   'armor': 400,
                                            'asteroidCapacity': 0,
                                            'capitalAbility': None,
                                            'category': 'CRUISER',
                                            'cloak': False,
                                            'cost': {   'crystal': 12000,
                                                        'eonium': 8000,
                                                        'metal': 20000},
                                            'damage': 0,
                                            'empDamage': 0,
                                            'empResistance': 20,
                                            'faction': 'VANGUARD',
                                            'gun': 0,
                                            'id': 'main-vanguard-fortress-transport',
                                            'init': 12,
                                            'name': 'Fortress Transport',
                                            'resourceCapacity': 200000,
                                            'shipClass': 'HEAVY',
                                            'targetClass1': 'RESOURCES',
                                            'targetClass2': '',
                                            'targetClass3': ''},
    'main-vanguard-guardian': {   'armor': 94,
                                  'asteroidCapacity': 0,
                                  'capitalAbility': None,
                                  'category': 'FRIGATE',
                                  'cloak': False,
                                  'cost': {   'crystal': 1900,
                                              'eonium': 1200,
                                              'metal': 3000},
                                  'damage': 58,
                                  'empDamage': 0,
                                  'empResistance': 14,
                                  'faction': 'VANGUARD',
                                  'gun': 17,
                                  'id': 'main-vanguard-guardian',
                                  'init': 4,
                                  'name': 'Guardian',
                                  'resourceCapacity': 0,
                                  'shipClass': 'MEDIUM',
                                  'targetClass1': 'HEAVY',
                                  'targetClass2': 'MEDIUM',
                                  'targetClass3': 'LIGHT'},
    'main-vanguard-imperator': {   'armor': 720,
                                   'asteroidCapacity': 0,
                                   'capitalAbility': {   'maxAbsorptionPercent': 25,
                                                         'shieldAbsorptionPercent': 8,
                                                         'type': 'shield_aura'},
                                   'category': 'BATTLESHIP',
                                   'cloak': False,
                                   'cost': {   'crystal': 22000,
                                               'eonium': 17000,
                                               'metal': 34000},
                                   'damage': 170,
                                   'empDamage': 0,
                                   'empResistance': 45,
                                   'faction': 'VANGUARD',
                                   'gun': 42,
                                   'id': 'main-vanguard-imperator',
                                   'init': 11,
                                   'name': 'Imperator',
                                   'resourceCapacity': 0,
                                   'shipClass': 'SPECIAL',
                                   'targetClass1': 'HEAVY',
                                   'targetClass2': 'MEDIUM',
                                   'targetClass3': 'LIGHT'},
    'main-vanguard-ironclad-freighter': {   'armor': 220,
                                            'asteroidCapacity': 0,
                                            'capitalAbility': None,
                                            'category': 'CRUISER',
                                            'cloak': False,
                                            'cost': {   'crystal': 6000,
                                                        'eonium': 4000,
                                                        'metal': 12000},
                                            'damage': 0,
                                            'empDamage': 0,
                                            'empResistance': 15,
                                            'faction': 'VANGUARD',
                                            'gun': 0,
                                            'id': 'main-vanguard-ironclad-freighter',
                                            'init': 12,
                                            'name': 'Ironclad Freighter',
                                            'resourceCapacity': 100000,
                                            'shipClass': 'HEAVY',
                                            'targetClass1': 'RESOURCES',
                                            'targetClass2': '',
                                            'targetClass3': ''},
    'main-vanguard-ore-extractor': {   'armor': 200,
                                       'asteroidCapacity': 5,
                                       'capitalAbility': None,
                                       'category': 'FRIGATE',
                                       'cloak': False,
                                       'cost': {   'crystal': 6000,
                                                   'eonium': 4000,
                                                   'metal': 10000},
                                       'damage': 0,
                                       'empDamage': 0,
                                       'empResistance': 10,
                                       'faction': 'VANGUARD',
                                       'gun': 0,
                                       'id': 'main-vanguard-ore-extractor',
                                       'init': 12,
                                       'name': 'Ore Extractor',
                                       'resourceCapacity': 0,
                                       'shipClass': 'MEDIUM',
                                       'targetClass1': 'ROIDS',
                                       'targetClass2': '',
                                       'targetClass3': ''},
    'main-vanguard-sentinel': {   'armor': 116,
                                  'asteroidCapacity': 0,
                                  'capitalAbility': None,
                                  'category': 'DESTROYER',
                                  'cloak': False,
                                  'cost': {   'crystal': 2400,
                                              'eonium': 1500,
                                              'metal': 3800},
                                  'damage': 72,
                                  'empDamage': 0,
                                  'empResistance': 16,
                                  'faction': 'VANGUARD',
                                  'gun': 19,
                                  'id': 'main-vanguard-sentinel',
                                  'init': 4,
                                  'name': 'Sentinel',
                                  'resourceCapacity': 0,
                                  'shipClass': 'MEDIUM',
                                  'targetClass1': 'LIGHT',
                                  'targetClass2': 'MEDIUM',
                                  'targetClass3': 'HEAVY'},
    'main-vanguard-siege-harvester': {   'armor': 380,
                                         'asteroidCapacity': 18,
                                         'capitalAbility': None,
                                         'category': 'CRUISER',
                                         'cloak': False,
                                         'cost': {   'crystal': 13000,
                                                     'eonium': 9000,
                                                     'metal': 22000},
                                         'damage': 0,
                                         'empDamage': 0,
                                         'empResistance': 20,
                                         'faction': 'VANGUARD',
                                         'gun': 0,
                                         'id': 'main-vanguard-siege-harvester',
                                         'init': 12,
                                         'name': 'Siege Harvester',
                                         'resourceCapacity': 0,
                                         'shipClass': 'HEAVY',
                                         'targetClass1': 'ROIDS',
                                         'targetClass2': '',
                                         'targetClass3': ''},
    'main-vanguard-sovereign': {   'armor': 420,
                                   'asteroidCapacity': 0,
                                   'capitalAbility': None,
                                   'category': 'BATTLESHIP',
                                   'cloak': False,
                                   'cost': {   'crystal': 9900,
                                               'eonium': 7200,
                                               'metal': 14400},
                                   'damage': 200,
                                   'empDamage': 0,
                                   'empResistance': 35,
                                   'faction': 'VANGUARD',
                                   'gun': 34,
                                   'id': 'main-vanguard-sovereign',
                                   'init': 6,
                                   'name': 'Sovereign',
                                   'resourceCapacity': 0,
                                   'shipClass': 'HEAVY',
                                   'targetClass1': 'MEDIUM',
                                   'targetClass2': 'HEAVY',
                                   'targetClass3': 'LIGHT'},
    'main-vanguard-supply-runner': {   'armor': 150,
                                       'asteroidCapacity': 0,
                                       'capitalAbility': None,
                                       'category': 'FRIGATE',
                                       'cloak': False,
                                       'cost': {   'crystal': 4000,
                                                   'eonium': 2500,
                                                   'metal': 8000},
                                       'damage': 0,
                                       'empDamage': 0,
                                       'empResistance': 10,
                                       'faction': 'VANGUARD',
                                       'gun': 0,
                                       'id': 'main-vanguard-supply-runner',
                                       'init': 12,
                                       'name': 'Supply Runner',
                                       'resourceCapacity': 50000,
                                       'shipClass': 'MEDIUM',
                                       'targetClass1': 'RESOURCES',
                                       'targetClass2': '',
                                       'targetClass3': ''},
    'main-vanguard-titan': {   'armor': 250,
                               'asteroidCapacity': 0,
                               'capitalAbility': None,
                               'category': 'CRUISER',
                               'cloak': False,
                               'cost': {   'crystal': 4900,
                                           'eonium': 3500,
                                           'metal': 7800},
                               'damage': 112,
                               'empDamage': 0,
                               'empResistance': 24,
                               'faction': 'VANGUARD',
                               'gun': 25,
                               'id': 'main-vanguard-titan',
                               'init': 5,
                               'name': 'Titan',
                               'resourceCapacity': 0,
                               'shipClass': 'HEAVY',
                               'targetClass1': 'MEDIUM',
                               'targetClass2': 'HEAVY',
                               'targetClass3': 'LIGHT'}}

# --- PDS (Planetary Defense Structures) Combat Definitions ---
PDS_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "main-ion-cannon": {
        "id": "main-ion-cannon", "name": "Ion Cannon", "category": "PDS", "shipClass": "PDS",
        "armor": 893, "gun": 17, "damage": 189, "init": 1,
        "targetClass1": "HEAVY", "targetClass2": "MEDIUM", "targetClass3": "LIGHT",
        "cost": {"metal": 20000, "crystal": 15000, "eonium": 10000}
    },
    "main-missile-silo": {
        "id": "main-missile-silo", "name": "Missile Silo", "category": "PDS", "shipClass": "PDS",
        "armor": 546, "gun": 15, "damage": 116, "init": 2,
        "targetClass1": "MEDIUM", "targetClass2": "HEAVY", "targetClass3": "LIGHT",
        "cost": {"metal": 12000, "crystal": 8000, "eonium": 5000}
    },
    "main-laser-battery": {
        "id": "main-laser-battery", "name": "Laser Battery", "category": "PDS", "shipClass": "PDS",
        "armor": 336, "gun": 13, "damage": 74, "init": 3,
        "targetClass1": "LIGHT", "targetClass2": "MEDIUM", "targetClass3": "HEAVY",
        "cost": {"metal": 8000, "crystal": 5000, "eonium": 3000}
    },
    "main-shield-generator": {
        "id": "main-shield-generator", "name": "Shield Generator", "category": "PDS", "shipClass": "PDS",
        "armor": 683, "gun": 0, "damage": 0, "init": 0,
        "maxAbsorption": 50, "absorptionPerLevel": 10,
        "targetClass1": "", "targetClass2": "", "targetClass3": "",
        "cost": {"metal": 15000, "crystal": 12000, "eonium": 8000}
    },
    "main-sensor-array": {
        "id": "main-sensor-array", "name": "Sensor Array", "category": "PDS", "shipClass": "PDS",
        "armor": 30, "gun": 0, "damage": 0, "init": 0,
        "targetClass1": "", "targetClass2": "", "targetClass3": "",
        "cost": {"metal": 10000, "crystal": 15000, "eonium": 5000}
    }
}


@dataclass
class CombatGroup:
    unit_id: str
    name: str
    count: int
    armor: float
    gun: float
    damage: float
    emp_damage: float
    emp_resistance: float
    init: int
    ship_class: str
    target_class1: str
    target_class2: str
    target_class3: str
    side: str  # "attacker" or "defender"
    is_pds: bool = False
    is_shield: bool = False
    current_hp: float = 0.0
    emp_disabled: bool = False
    cost: Dict[str, int] = field(default_factory=dict)
    resource_capacity: int = 0
    asteroid_capacity: int = 0
    capital_ability: Optional[Dict[str, Any]] = None
    cloak: bool = False
    fleet_id: str = ""
    fleet_name: str = ""
    initial_count: int = 0

    def __post_init__(self):
        if self.initial_count == 0 and self.count > 0:
            self.initial_count = self.count


def parse_scan_record(scan_raw: Any, planet_lookup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts coordinates, owner, named fleets, garrison, PDS, and research
    from any scan record (DEEP_SCAN, MILITARY_SCAN, FLEET_COMPOSITION_SCAN, INCOMING_SCAN, etc.)
    returned by get_scan_history.
    """
    if not scan_raw:
        return {}

    # Extract targetPlanetId and result
    target_id = scan_raw.get("targetPlanetId") or scan_raw.get("planetId") or ""
    scan_type = scan_raw.get("scanType", "DEEP_SCAN")
    scan_id = scan_raw.get("id", "")
    tick = scan_raw.get("tick", 0)
    created_at = scan_raw.get("createdAt", "")

    res_raw = scan_raw.get("result", {})
    if isinstance(res_raw, str):
        try:
            res = json.loads(res_raw)
        except Exception:
            res = {}
    elif isinstance(res_raw, dict):
        res = res_raw
    else:
        res = {}

    coords = res.get("coords") or scan_raw.get("coords")
    owner = res.get("ownerPlayerId") or scan_raw.get("ownerPlayerId") or scan_raw.get("owner")
    population = int(res.get("population", 0))

    # Scanned resources & asteroids
    resources = {
        "metal": int(res.get("metal", 0)),
        "crystal": int(res.get("crystal", 0)),
        "eonium": int(res.get("eonium", 0)),
    }
    asteroids = res.get("asteroids", {"metalRoids": 0, "crystalRoids": 0, "eoniumRoids": 0})

    # Named fleets docked or in transit at planet
    named_fleets: List[Dict[str, Any]] = []
    for nf in res.get("namedFleets", []):
        named_fleets.append({
            "id": nf.get("id"),
            "name": nf.get("name", "Unnamed Fleet"),
            "ships": nf.get("ships", {}),
            "status": nf.get("status", "DOCKED")
        })

    for tf in res.get("transitFleets", []):
        named_fleets.append({
            "id": tf.get("id"),
            "name": (tf.get("name") or "Transit Fleet") + " (In Transit)",
            "ships": tf.get("ships", {}),
            "status": "TRANSIT"
        })

    # PDS constructions and levels
    pds_levels: Dict[str, int] = {}
    for c in res.get("constructions", []):
        c_name = c.get("name", "")
        lvl = c.get("level", 0)
        if any(k in c_name.lower() for k in ["laser", "missile", "ion", "shield", "sensor"]):
            pds_levels[c_name] = lvl

    # Docked ships / garrison (separate PDS structure units if present)
    raw_ships = res.get("ships", {})
    if not raw_ships and isinstance(res.get("fleet"), dict):
        raw_ships = res.get("fleet", {})

    garrison_ships: Dict[str, int] = {}
    for s_id, cnt in raw_ships.items():
        try:
            cnt_int = int(cnt)
        except (ValueError, TypeError):
            continue
        if s_id.startswith("pds-"):
            s_lower = s_id.lower()
            if "laser" in s_lower:
                pds_levels["Laser Battery"] = max(pds_levels.get("Laser Battery", 0), cnt_int)
            elif "missile" in s_lower:
                pds_levels["Missile Silo"] = max(pds_levels.get("Missile Silo", 0), cnt_int)
            elif "ion" in s_lower:
                pds_levels["Ion Cannon"] = max(pds_levels.get("Ion Cannon", 0), cnt_int)
            elif "shield" in s_lower:
                pds_levels["Shield Generator"] = max(pds_levels.get("Shield Generator", 0), cnt_int)
        else:
            garrison_ships[s_id] = cnt_int

    # Tech research levels
    research_levels: Dict[str, int] = {}
    for r in res.get("research", []):
        r_name = r.get("name", "")
        lvl = r.get("level", 0)
        if any(k in r_name.lower() for k in ["hull", "pds", "ship tech", "engineering"]):
            research_levels[r_name] = lvl

    # Lookup fallback if targetPlanetId metadata is provided
    if planet_lookup and target_id in planet_lookup:
        meta = planet_lookup[target_id]
        if (not coords or coords == "Unknown") and meta.get("coords"):
            coords = meta["coords"]
        if (not owner or owner == "Unknown") and meta.get("owner"):
            owner = meta["owner"]
        if not pds_levels and meta.get("pds"):
            pds_levels = dict(meta["pds"])
        if not research_levels and meta.get("research"):
            research_levels = dict(meta["research"])
        if not any(resources.values()) and meta.get("resources"):
            resources = dict(meta["resources"])
        if not any(asteroids.values()) and meta.get("asteroids"):
            asteroids = dict(meta["asteroids"])
        if not owner or owner == "Unknown":
            owner = meta.get("owner") or owner

    planet_name = ""
    if planet_lookup and target_id in planet_lookup:
        planet_name = planet_lookup[target_id].get("name", "")

    source = scan_raw.get("source", "user")
    alliance_id = scan_raw.get("allianceId", "")
    alliance_tag = scan_raw.get("allianceTag", "")
    scanner_name = scan_raw.get("scannerPlayerName", "") or scan_raw.get("scannerPlanetId", "")

    return {
        "targetPlanetId": target_id,
        "coords": coords or "Unknown",
        "owner": owner or "Unknown",
        "planetName": planet_name,
        "population": population,
        "resources": resources,
        "asteroids": asteroids,
        "namedFleets": named_fleets,
        "garrisonShips": garrison_ships,
        "pds": pds_levels,
        "research": research_levels,
        "tick": tick,
        "createdAt": created_at,
        "scanType": scan_type,
        "scanId": scan_id,
        "status": scan_raw.get("status", "success"),
        "isBlocked": (scan_raw.get("status") == "blocked"),
        "source": source,
        "allianceId": alliance_id,
        "allianceTag": alliance_tag,
        "scannerPlayerName": scanner_name,
    }


parse_deep_scan = parse_scan_record



def simulate_combat(
    attacker_fleet: Optional[Dict[str, int]] = None,
    defender_fleet: Optional[Dict[str, int]] = None,
    defender_pds: Optional[Dict[str, int]] = None,
    attacker_research: Optional[Dict[str, int]] = None,
    defender_research: Optional[Dict[str, int]] = None,
    defender_resources: Optional[Dict[str, int]] = None,
    defender_asteroids: Optional[Dict[str, int]] = None,
    max_rounds: int = 1,
    def_armor_mult: Optional[float] = None,
    atk_armor_mult: Optional[float] = None,
    attacker_fleets: Optional[List[Dict[str, Any]]] = None,
    defender_fleets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Executes a complete round-by-round combat simulation between two forces.
    Supports single fleets or multiple coalition fleets (joint strike / allied defense).
    Returns detailed casualties (overall & per-fleet), victory confidence, plunder forecast,
    asteroid theft, score change, and event replay.
    """
    attacker_research = attacker_research or {}
    defender_research = defender_research or {}
    defender_pds = defender_pds or {}
    defender_resources = defender_resources or {}
    defender_asteroids = defender_asteroids or {}

    # Research bonuses (Pegasus Galaxy official: Hulls +5% armor/lvl, PDS +3% damage/lvl)
    atk_hull_lvl = attacker_research.get("Hulls", 0)
    def_hull_lvl = defender_research.get("Hulls", 0)
    def_pds_lvl = defender_research.get("PDS", 0)
    atk_pds_lvl = attacker_research.get("PDS", 0)

    if atk_armor_mult is None:
        # Attackers do not have home bonus (1.0)
        atk_armor_mult = 1.0 + (atk_hull_lvl * 0.05)
    if def_armor_mult is None:
        # Official Formula: Armor = floor(baseArmor * homeBonus * researchBonus)
        # Home Bonus = 1.10 (only when defending at home), Research Bonus = 1 + (Hulls * 0.05)
        def_home_bonus = 1.10 if (defender_pds or def_hull_lvl >= 0) else 1.0
        def_armor_mult = def_home_bonus * (1.0 + (def_hull_lvl * 0.05))
    pds_mult = 1.0 + (def_pds_lvl * 0.03)

    # Normalize multiple fleet inputs
    if attacker_fleets is None:
        attacker_fleets = [{
            "id": "atk_0",
            "name": "Attacker Fleet",
            "enabled": True,
            "ships": attacker_fleet or {}
        }]
    elif not attacker_fleets and attacker_fleet:
        attacker_fleets = [{
            "id": "atk_0",
            "name": "Attacker Fleet",
            "enabled": True,
            "ships": attacker_fleet
        }]

    if defender_fleets is None:
        defender_fleets = [{
            "id": "def_0",
            "name": "Defender Garrison",
            "enabled": True,
            "ships": defender_fleet or {}
        }]
    elif not defender_fleets and defender_fleet:
        defender_fleets = [{
            "id": "def_0",
            "name": "Defender Garrison",
            "enabled": True,
            "ships": defender_fleet
        }]

    # Initialize Combat Groups
    attacker_groups: List[CombatGroup] = []
    defender_groups: List[CombatGroup] = []

    # 1. Attacker Fleets (Each enabled fleet adds its ships tagged with fleet_id and fleet_name)
    for f_idx, fleet in enumerate(attacker_fleets):
        f_id = fleet.get("id") or f"atk_{f_idx}"
        f_name = fleet.get("name") or f"Attacker Fleet {f_idx + 1}"
        if not fleet.get("enabled", True):
            continue  # Disabled fleet takes 0 casualties and deals 0 damage

        for s_id, count in fleet.get("ships", {}).items():
            if count <= 0:
                continue
            def_info = SHIP_DEFINITIONS.get(s_id, {
                "name": s_id, "armor": 100, "gun": 10, "damage": 20,
                "empDamage": 0, "empResistance": 10, "init": 6,
                "shipClass": "MEDIUM", "targetClass1": "MEDIUM",
                "targetClass2": "LIGHT", "targetClass3": "HEAVY",
                "resourceCapacity": 0, "asteroidCapacity": 0, "cost": {"metal": 5000, "crystal": 2000, "eonium": 1000}
            })
            base_armor = math.floor(def_info.get("armor", 50) * atk_armor_mult)
            if def_info.get("damage", 0) == 0 and def_info.get("empDamage", 0) > 0:
                base_dmg = 0.0
            else:
                base_dmg = float(def_info.get("damage", 0)) if def_info.get("damage", 0) > 0 else (def_info.get("gun", 0) * 2.5)
            attacker_groups.append(CombatGroup(
                unit_id=s_id,
                name=def_info.get("name", s_id),
                count=count,
                armor=base_armor,
                gun=def_info.get("gun", 0),
                damage=base_dmg,
                emp_damage=def_info.get("empDamage", 0),
                emp_resistance=def_info.get("empResistance", 10),
                init=def_info.get("init", 6),
                ship_class=def_info.get("shipClass", "MEDIUM"),
                target_class1=def_info.get("targetClass1", "MEDIUM"),
                target_class2=def_info.get("targetClass2", "LIGHT"),
                target_class3=def_info.get("targetClass3", "HEAVY"),
                side="attacker",
                cost=def_info.get("cost", {}),
                resource_capacity=def_info.get("resourceCapacity", 0),
                asteroid_capacity=def_info.get("asteroidCapacity", 0),
                capital_ability=def_info.get("capitalAbility"),
                cloak=bool(def_info.get("cloak", False)),
                fleet_id=f_id,
                fleet_name=f_name
            ))

    # 2. Defender Fleets (Each enabled fleet adds its ships tagged with fleet_id and fleet_name)
    for f_idx, fleet in enumerate(defender_fleets):
        f_id = fleet.get("id") or f"def_{f_idx}"
        f_name = fleet.get("name") or f"Defender Fleet {f_idx + 1}"
        if not fleet.get("enabled", True):
            continue  # Disabled fleet takes 0 casualties and deals 0 damage

        for s_id, count in fleet.get("ships", {}).items():
            if count <= 0:
                continue
            def_info = SHIP_DEFINITIONS.get(s_id, {
                "name": s_id, "armor": 100, "gun": 10, "damage": 20,
                "empDamage": 0, "empResistance": 10, "init": 6,
                "shipClass": "MEDIUM", "targetClass1": "MEDIUM",
                "targetClass2": "LIGHT", "targetClass3": "HEAVY",
                "resourceCapacity": 0, "asteroidCapacity": 0, "cost": {"metal": 5000, "crystal": 2000, "eonium": 1000}
            })
            base_armor = math.floor(def_info.get("armor", 50) * def_armor_mult)
            if def_info.get("damage", 0) == 0 and def_info.get("empDamage", 0) > 0:
                base_dmg = 0.0
            else:
                base_dmg = float(def_info.get("damage", 0)) if def_info.get("damage", 0) > 0 else (def_info.get("gun", 0) * 2.5)
            defender_groups.append(CombatGroup(
                unit_id=s_id,
                name=def_info.get("name", s_id),
                count=count,
                armor=base_armor,
                gun=def_info.get("gun", 0),
                damage=base_dmg,
                emp_damage=def_info.get("empDamage", 0),
                emp_resistance=def_info.get("empResistance", 10),
                init=def_info.get("init", 6),
                ship_class=def_info.get("shipClass", "MEDIUM"),
                target_class1=def_info.get("targetClass1", "MEDIUM"),
                target_class2=def_info.get("targetClass2", "LIGHT"),
                target_class3=def_info.get("targetClass3", "HEAVY"),
                side="defender",
                cost=def_info.get("cost", {}),
                resource_capacity=def_info.get("resourceCapacity", 0),
                asteroid_capacity=def_info.get("asteroidCapacity", 0),
                capital_ability=def_info.get("capitalAbility"),
                cloak=bool(def_info.get("cloak", False)),
                fleet_id=f_id,
                fleet_name=f_name
            ))

    # 3. Defender PDS
    shield_absorption_pct = 0.0
    shield_max_hp = 0.0

    for pds_key, level in defender_pds.items():
        if level <= 0:
            continue
        # Map key to standard definition
        matched_id = None
        for pid in PDS_DEFINITIONS:
            if pid.replace("main-", "").replace("-", " ") in pds_key.lower() or pds_key.lower() in pid.replace("main-", ""):
                matched_id = pid
                break
        if not matched_id and "shield" in pds_key.lower():
            matched_id = "main-shield-generator"
        elif not matched_id and "ion" in pds_key.lower():
            matched_id = "main-ion-cannon"
        elif not matched_id and ("missile" in pds_key.lower() or "silo" in pds_key.lower()):
            matched_id = "main-missile-silo"
        elif not matched_id and "laser" in pds_key.lower():
            matched_id = "main-laser-battery"

        if matched_id and matched_id in PDS_DEFINITIONS:
            p_def = PDS_DEFINITIONS[matched_id]
            if matched_id == "main-shield-generator":
                shield_absorption_pct = min(0.50, level * 0.10)
                shield_max_hp = p_def["armor"] * level * pds_mult
            else:
                pds_dmg = p_def.get("damage", 80) * level * pds_mult
                pds_armor = p_def.get("armor", 300) * level * pds_mult
                defender_groups.append(CombatGroup(
                    unit_id=matched_id,
                    name=p_def["name"],
                    count=level,
                    armor=pds_armor,
                    gun=p_def.get("gun", 15) * level,
                    damage=pds_dmg,
                    emp_damage=0,
                    emp_resistance=50,
                    init=p_def.get("init", 2),
                    ship_class="PDS",
                    target_class1=p_def.get("targetClass1", "HEAVY"),
                    target_class2=p_def.get("targetClass2", "MEDIUM"),
                    target_class3=p_def.get("targetClass3", "LIGHT"),
                    side="defender",
                    is_pds=True,
                    cost=p_def.get("cost", {}),
                    fleet_id="def_pds",
                    fleet_name="Planetary Defenses"
                ))

    # Record Initial Totals for Summary
    atk_start_counts: Dict[str, int] = {}
    for g in attacker_groups:
        atk_start_counts[g.unit_id] = atk_start_counts.get(g.unit_id, 0) + g.count

    def_start_counts: Dict[str, int] = {}
    for g in defender_groups:
        def_start_counts[g.unit_id] = def_start_counts.get(g.unit_id, 0) + g.count

    round_details: List[Dict[str, Any]] = []
    current_shield_hp = shield_max_hp

    # --- Combat Round Loop ---
    for r_num in range(1, max_rounds + 1):
        # Check active units
        live_atk = [g for g in attacker_groups if g.count > 0]
        live_def = [g for g in defender_groups if g.count > 0]

        if not live_atk or not live_def:
            break

        round_events: List[str] = []
        round_actions: List[Dict[str, Any]] = []

        # Calculate Imperator Shield Aura for each side (8% per Imperator, max 25%)
        atk_imperator_count = sum(g.count for g in live_atk if g.unit_id == "main-vanguard-imperator")
        def_imperator_count = sum(g.count for g in live_def if g.unit_id == "main-vanguard-imperator")
        atk_aura_pct = min(0.25, atk_imperator_count * 0.08)
        def_aura_pct = min(0.25, def_imperator_count * 0.08)

        # Track total damage absorbed by Imperator Shield Aura to apply structural damage to Imperators
        atk_absorbed_by_aura_total = 0.0
        def_absorbed_by_aura_total = 0.0

        # Gather all units and sort by initiative (lower initiative fires first; attacker fires first on ties)
        all_units = live_atk + live_def
        all_units.sort(key=lambda u: (u.init, 0 if u.side == "attacker" else 1))

        for shooter in all_units:
            if shooter.count <= 0 or shooter.emp_disabled:
                continue

            target_side = "defender" if shooter.side == "attacker" else "attacker"
            enemies = [e for e in (live_def if target_side == "defender" else live_atk) if e.count > 0]

            if not enemies:
                break

            # 1. Target Priority Candidate Selection (ordered by preference, taking Cloak into account in Round 1)
            targetable_enemies = enemies
            if r_num == 1:
                # Cloaked ships (like Synthara Oracle) cannot be targeted in round 1 if other ships exist
                uncloaked = [e for e in enemies if not e.cloak]
                if uncloaked:
                    targetable_enemies = uncloaked

            # Select SINGLE ACTIVE target class according to shooter's target priority classes
            # A ship group engages targets strictly from its highest available priority class in this round
            # SPECIAL capital ships (Imperator, Oblivion, Oracle) are screened behind standard battleline ships
            # Pegasus Galaxy official target efficiency:
            # Primary (1st) = 100%, Secondary (2nd) = 80%, Tertiary (3rd) = 70%, Fallback = 100%
            target_candidates: List[CombatGroup] = []
            target_efficiency: float = 1.0

            for p_idx, p_class in enumerate([shooter.target_class1, shooter.target_class2, shooter.target_class3]):
                if not p_class:
                    continue
                matching = [e for e in targetable_enemies if e.ship_class == p_class]
                if matching:
                    target_candidates = matching
                    target_efficiency = 1.0 if p_idx == 0 else (0.80 if p_idx == 1 else 0.70)
                    break
                elif p_class == 'HEAVY':
                    # If all standard HEAVY ships are down, engage screened SPECIAL capital ships
                    matching_special = [e for e in targetable_enemies if e.ship_class == 'SPECIAL']
                    if matching_special:
                        target_candidates = matching_special
                        target_efficiency = 1.0 if p_idx == 0 else (0.80 if p_idx == 1 else 0.70)
                        break

            # If none of the 3 priority classes have targets, fallback to any remaining enemy targets at 100%
            if not target_candidates:
                target_candidates = sorted(targetable_enemies, key=lambda e: (1 if e.ship_class == 'SPECIAL' else 0))
                target_efficiency = 1.0

            if not target_candidates:
                continue

            # 2. Damage Output Calculation & Kinetic Spillover (quantity * damage * targetEfficiency)
            raw_firepower = shooter.count * shooter.damage * target_efficiency
            total_dmg = raw_firepower

            # 3. Shield Absorption (Planetary Shield Generator for defender targets)
            absorbed_pds = 0.0
            if target_side == "defender" and current_shield_hp > 0 and shield_absorption_pct > 0:
                potential_absorb = total_dmg * shield_absorption_pct
                absorbed_pds = min(potential_absorb, current_shield_hp)
                current_shield_hp -= absorbed_pds
                total_dmg -= absorbed_pds

            # 4. Imperator Shield Aura Absorption (Fleet-wide protection: 8% per Imperator, max 25%)
            absorbed_aura = 0.0
            aura_pct = def_aura_pct if target_side == "defender" else atk_aura_pct
            if aura_pct > 0 and total_dmg > 0:
                absorbed_aura = total_dmg * aura_pct
                total_dmg -= absorbed_aura
                if target_side == "attacker":
                    atk_absorbed_by_aura_total += absorbed_aura
                else:
                    def_absorbed_by_aura_total += absorbed_aura

            # 5. Casualty & Damage Spillover across targets
            if shooter.damage > 0 and total_dmg > 0:
                remaining_dmg = total_dmg
                for chosen_target in target_candidates:
                    if remaining_dmg <= 0:
                        break
                    if chosen_target.count <= 0:
                        continue

                    # Calculate how many ships of this target group can be destroyed with remaining damage
                    destroyed = min(chosen_target.count, int(remaining_dmg // chosen_target.armor))
                    if destroyed == 0 and remaining_dmg > (chosen_target.armor * 0.75):
                        destroyed = 1

                    dmg_used = min(remaining_dmg, destroyed * chosen_target.armor)
                    if destroyed == 0 and dmg_used == 0:
                        # Cannot destroy even 1 ship, damage expends against armor or carries over
                        break

                    chosen_target.count -= destroyed
                    remaining_dmg -= dmg_used

                    eff_note = f" ({int(target_efficiency * 100)}% eff)" if target_efficiency < 1.0 else ""
                    side_label = "🛡️ Defender" if shooter.side == "defender" else "🚀 Attacker"
                    shooter_label = f"[{shooter.fleet_name}] {shooter.count:,}x {shooter.name}" if shooter.fleet_name else f"{shooter.count:,}x {shooter.name}"
                    target_label = f"[{chosen_target.fleet_name}] {chosen_target.name}" if chosen_target.fleet_name else chosen_target.name
                    msg = f"{side_label} {shooter_label} (Init {shooter.init}) fired at {target_label} -> dealt {int(dmg_used):,} dmg{eff_note}"
                    if destroyed > 0:
                        msg += f", destroyed {destroyed:,} ships"
                    else:
                        msg += f", 0 destroyed ({chosen_target.count:,} remaining)"
                    round_events.append(msg)

                    action_data = {
                        "firingShipGroup": shooter.name,
                        "firingFleet": shooter.fleet_name,
                        "firingCount": shooter.count,
                        "init": shooter.init,
                        "side": shooter.side,
                        "targetShipGroup": chosen_target.name,
                        "targetFleet": chosen_target.fleet_name,
                        "targetSide": target_side,
                        "damageDealt": int(dmg_used),
                        "damageAbsorbed": int(absorbed_pds + absorbed_aura) if len(round_actions) == 0 else 0,
                        "shipsDestroyed": destroyed,
                        "shipsEmped": 0,
                        "empResult": {"status": "not_attempted"}
                    }
                    round_actions.append(action_data)

                    # Oblivion Siege Barrier (Reflects 15% of kinetic damage back at attacker)
                    if chosen_target.unit_id == "main-ashkari-oblivion" and dmg_used > 0:
                        reflected_dmg = dmg_used * 0.15
                        shooter_destroyed = min(shooter.count, int(reflected_dmg // shooter.armor))
                        if shooter_destroyed == 0 and reflected_dmg > (shooter.armor * 0.75):
                            shooter_destroyed = 1
                        shooter.count -= shooter_destroyed
                        reflect_msg = f"🛡️ Oblivion Siege Barrier reflected {int(reflected_dmg):,} damage back to {shooter.name}"
                        if shooter_destroyed > 0:
                            reflect_msg += f", destroyed {shooter_destroyed:,}"
                        round_events.append(reflect_msg)

            # 6. EMP Disruption Spillover (if firing group has EMP weapons)
            # Pegasus Galaxy official: Chance = max(0.0, min(1.0, 0.5 - (targetEmpRes / 100)))
            if shooter.emp_damage > 0:
                remaining_emp = shooter.count * shooter.emp_damage
                for chosen_target in target_candidates:
                    if remaining_emp <= 0:
                        break
                    if chosen_target.count <= 0 or chosen_target.emp_disabled:
                        continue

                    # Oblivion / 100% resistance check
                    if chosen_target.emp_resistance >= 100:
                        action_data = {
                            "firingShipGroup": shooter.name,
                            "side": shooter.side,
                            "targetShipGroup": chosen_target.name,
                            "targetSide": target_side,
                            "damageDealt": 0,
                            "damageAbsorbed": 0,
                            "shipsDestroyed": 0,
                            "shipsEmped": 0,
                            "empResult": {"status": "resisted"}
                        }
                        round_actions.append(action_data)
                        round_events.append(f"🛡️ {chosen_target.name} resisted EMP disruption from {shooter.name}")
                        continue

                    # Official EMP chance per unit: Chance = 0.5 - (targetEmpRes / 100), clamped [0, 1]
                    emp_chance = max(0.0, min(1.0, 0.5 - (chosen_target.emp_resistance / 100.0)))
                    expected_disabled = int(round(chosen_target.count * emp_chance)) if emp_chance > 0 else 0

                    if expected_disabled > 0 and not chosen_target.is_pds:
                        chosen_target.emp_disabled = True
                        action_data = {
                            "firingShipGroup": shooter.name,
                            "side": shooter.side,
                            "targetShipGroup": chosen_target.name,
                            "targetSide": target_side,
                            "damageDealt": 0,
                            "damageAbsorbed": 0,
                            "shipsDestroyed": 0,
                            "shipsEmped": expected_disabled,
                            "empResult": {"status": "disabled"}
                        }
                        round_actions.append(action_data)
                        round_events.append(f"⚡ {shooter.name} EMP disrupted {expected_disabled}/{chosen_target.count} {chosen_target.name} ({int(emp_chance * 100)}% chance)")
                        break
                    else:
                        # Resisted
                        action_data = {
                            "firingShipGroup": shooter.name,
                            "side": shooter.side,
                            "targetShipGroup": chosen_target.name,
                            "targetSide": target_side,
                            "damageDealt": 0,
                            "damageAbsorbed": 0,
                            "shipsDestroyed": 0,
                            "shipsEmped": 0,
                            "empResult": {"status": "resisted"}
                        }
                        round_actions.append(action_data)
                        round_events.append(f"🛡️ {chosen_target.name} resisted EMP disruption from {shooter.name}")
                        break

        # Apply absorbed aura damage to protecting Imperators (8% per Imperator, max 25%)
        if atk_absorbed_by_aura_total > 0:
            atk_imp = next((g for g in live_atk if g.unit_id == "main-vanguard-imperator" and g.count > 0), None)
            if atk_imp:
                imp_lost = min(atk_imp.count, int(round(atk_absorbed_by_aura_total / atk_imp.armor)))
                if imp_lost > 0:
                    atk_imp.count -= imp_lost
                    round_events.append(f"🛡️ Attacker Imperator Shield Aura absorbed {int(atk_absorbed_by_aura_total):,} fleet damage ({imp_lost} Imperators destroyed from structural stress)")
                    round_actions.append({
                        "firingShipGroup": "Shield Aura Absorption",
                        "side": "defender",
                        "targetShipGroup": "Imperator",
                        "targetSide": "attacker",
                        "damageDealt": int(atk_absorbed_by_aura_total),
                        "damageAbsorbed": 0,
                        "shipsDestroyed": imp_lost,
                        "shipsEmped": 0,
                        "empResult": {"status": "not_attempted"}
                    })

        if def_absorbed_by_aura_total > 0:
            def_imp = next((g for g in live_def if g.unit_id == "main-vanguard-imperator" and g.count > 0), None)
            if def_imp:
                imp_lost = min(def_imp.count, int(round(def_absorbed_by_aura_total / def_imp.armor)))
                if imp_lost > 0:
                    def_imp.count -= imp_lost
                    round_events.append(f"🛡️ Defender Imperator Shield Aura absorbed {int(def_absorbed_by_aura_total):,} fleet damage ({imp_lost} Imperators destroyed from structural stress)")
                    round_actions.append({
                        "firingShipGroup": "Shield Aura Absorption",
                        "side": "attacker",
                        "targetShipGroup": "Imperator",
                        "targetSide": "defender",
                        "damageDealt": int(def_absorbed_by_aura_total),
                        "damageAbsorbed": 0,
                        "shipsDestroyed": imp_lost,
                        "shipsEmped": 0,
                        "empResult": {"status": "not_attempted"}
                    })

        # Reset EMP disable flags at end of round
        for g in all_units:
            g.emp_disabled = False

        # Record round details
        round_details.append({
            "roundNumber": r_num,
            "events": round_events,
            "actions": round_actions,
            "attackerRemaining": {g.unit_id: g.count for g in live_atk if g.count > 0},
            "defenderRemaining": {g.unit_id: g.count for g in live_def if g.count > 0},
            "shieldRemainingHP": int(max(0, current_shield_hp))
        })

    # --- Battle Outcome Evaluation ---
    surviving_atk: Dict[str, int] = {}
    for g in attacker_groups:
        surviving_atk[g.unit_id] = surviving_atk.get(g.unit_id, 0) + max(0, g.count)

    surviving_def: Dict[str, int] = {}
    for g in defender_groups:
        surviving_def[g.unit_id] = surviving_def.get(g.unit_id, 0) + max(0, g.count)

    atk_lost_counts = {u_id: max(0, atk_start_counts[u_id] - surviving_atk.get(u_id, 0)) for u_id in atk_start_counts}
    def_lost_counts = {u_id: max(0, def_start_counts[u_id] - surviving_def.get(u_id, 0)) for u_id in def_start_counts}

    total_atk_start = sum(atk_start_counts.values())
    total_atk_lost = sum(atk_lost_counts.values())
    total_atk_survived = total_atk_start - total_atk_lost

    total_def_start = sum(def_start_counts.values())
    total_def_lost = sum(def_lost_counts.values())
    total_def_survived = total_def_start - total_def_lost

    if total_def_survived == 0 and total_atk_survived > 0:
        outcome = "attacker"
        outcome_detail = "Attacker Decisive Victory"
    elif total_atk_survived == 0 and total_def_survived > 0:
        outcome = "defender"
        outcome_detail = "Defender Decisive Victory"
    elif total_def_lost > total_atk_lost * 1.5:
        outcome = "attacker"
        outcome_detail = "Attacker Pyrrhic Victory"
    elif total_atk_lost > total_def_lost * 1.5:
        outcome = "defender"
        outcome_detail = "Defender Repelled Assault"
    else:
        outcome = "draw"
        outcome_detail = "Tactical Stalemate / Ceasefire"

    # Value calculations
    def compute_value(lost_dict: Dict[str, int], lookup_defs: List[CombatGroup]) -> Dict[str, int]:
        m, c, e = 0, 0, 0
        def_map = {g.unit_id: g.cost for g in lookup_defs}
        for u_id, count in lost_dict.items():
            cost = def_map.get(u_id) or SHIP_DEFINITIONS.get(u_id, {}).get("cost", {})
            m += cost.get("metal", 0) * count
            c += cost.get("crystal", 0) * count
            e += cost.get("eonium", 0) * count
        return {"metal": m, "crystal": c, "eonium": e, "total": m + c + e}

    atk_val_lost = compute_value(atk_lost_counts, attacker_groups)
    def_val_lost = compute_value(def_lost_counts, defender_groups)

    # Build per-fleet casualty breakdown for attackers
    atk_fleets_summary = []
    for f_idx, fleet in enumerate(attacker_fleets):
        f_id = fleet.get("id") or f"atk_{f_idx}"
        f_name = fleet.get("name") or f"Attacker Fleet {f_idx + 1}"
        f_enabled = fleet.get("enabled", True)
        f_groups = [g for g in attacker_groups if g.fleet_id == f_id]

        f_start: Dict[str, int] = {}
        f_survived: Dict[str, int] = {}
        f_lost: Dict[str, int] = {}

        if f_enabled:
            for g in f_groups:
                f_start[g.unit_id] = f_start.get(g.unit_id, 0) + g.initial_count
                f_survived[g.unit_id] = f_survived.get(g.unit_id, 0) + max(0, g.count)
            for u_id, s_cnt in f_start.items():
                f_lost[u_id] = max(0, s_cnt - f_survived.get(u_id, 0))
        else:
            for s_id, count in fleet.get("ships", {}).items():
                if count > 0:
                    f_start[s_id] = count
                    f_survived[s_id] = count
                    f_lost[s_id] = 0

        tot_start = sum(f_start.values())
        tot_lost = sum(f_lost.values())
        tot_surv = sum(f_survived.values())
        f_val_start = compute_value(f_start, f_groups)
        f_val_surv = compute_value(f_survived, f_groups)
        f_val_lost = compute_value(f_lost, f_groups)
        f_score_start = round(f_val_start["total"] / 9)
        f_score_lost = round(f_val_lost["total"] / 9)
        f_score_surv = round(f_val_surv["total"] / 9)

        atk_fleets_summary.append({
            "id": f_id,
            "name": f_name,
            "enabled": f_enabled,
            "startCounts": f_start,
            "lostCounts": f_lost,
            "survivedCounts": f_survived,
            "totalStart": tot_start,
            "totalLost": tot_lost,
            "totalSurvived": tot_surv,
            "lossPercent": round((tot_lost / tot_start * 100) if tot_start > 0 else 0, 1),
            "valueStart": f_val_start,
            "valueLost": f_val_lost,
            "valueSurvived": f_val_surv,
            "scoreStart": f_score_start,
            "scoreLost": f_score_lost,
            "scoreSurvived": f_score_surv,
            "scoreDynamics": -f_score_lost
        })

    # Build per-fleet casualty breakdown for defenders
    def_fleets_summary = []
    for f_idx, fleet in enumerate(defender_fleets):
        f_id = fleet.get("id") or f"def_{f_idx}"
        f_name = fleet.get("name") or f"Defender Fleet {f_idx + 1}"
        f_enabled = fleet.get("enabled", True)
        f_groups = [g for g in defender_groups if g.fleet_id == f_id and not g.is_pds]

        f_start = {}
        f_survived = {}
        f_lost = {}

        if f_enabled:
            for g in f_groups:
                f_start[g.unit_id] = f_start.get(g.unit_id, 0) + g.initial_count
                f_survived[g.unit_id] = f_survived.get(g.unit_id, 0) + max(0, g.count)
            for u_id, s_cnt in f_start.items():
                f_lost[u_id] = max(0, s_cnt - f_survived.get(u_id, 0))
        else:
            for s_id, count in fleet.get("ships", {}).items():
                if count > 0:
                    f_start[s_id] = count
                    f_survived[s_id] = count
                    f_lost[s_id] = 0

        tot_start = sum(f_start.values())
        tot_lost = sum(f_lost.values())
        tot_surv = sum(f_survived.values())
        f_val_start = compute_value(f_start, f_groups)
        f_val_surv = compute_value(f_survived, f_groups)
        f_val_lost = compute_value(f_lost, f_groups)
        f_score_start = round(f_val_start["total"] / 9)
        f_score_lost = round(f_val_lost["total"] / 9)
        f_score_surv = round(f_val_surv["total"] / 9)

        def_fleets_summary.append({
            "id": f_id,
            "name": f_name,
            "enabled": f_enabled,
            "startCounts": f_start,
            "lostCounts": f_lost,
            "survivedCounts": f_survived,
            "totalStart": tot_start,
            "totalLost": tot_lost,
            "totalSurvived": tot_surv,
            "lossPercent": round((tot_lost / tot_start * 100) if tot_start > 0 else 0, 1),
            "valueStart": f_val_start,
            "valueLost": f_val_lost,
            "valueSurvived": f_val_surv,
            "scoreStart": f_score_start,
            "scoreLost": f_score_lost,
            "scoreSurvived": f_score_surv,
            "scoreDynamics": -f_score_lost
        })

    # Include Defender PDS in def_fleets_summary if present
    pds_groups = [g for g in defender_groups if g.is_pds]
    if pds_groups:
        pds_start = {g.unit_id: g.initial_count for g in pds_groups}
        pds_surv = {g.unit_id: max(0, g.count) for g in pds_groups}
        pds_lost = {u_id: max(0, pds_start[u_id] - pds_surv.get(u_id, 0)) for u_id in pds_start}
        tot_start = sum(pds_start.values())
        tot_lost = sum(pds_lost.values())
        tot_surv = sum(pds_surv.values())
        pds_cost_map = {g.unit_id: g.cost for g in pds_groups}
        pds_val = {"metal": 0, "crystal": 0, "eonium": 0, "total": 0}
        pds_val_start = {"metal": 0, "crystal": 0, "eonium": 0, "total": 0}
        pds_val_surv = {"metal": 0, "crystal": 0, "eonium": 0, "total": 0}
        for u_id, cnt in pds_lost.items():
            c = pds_cost_map.get(u_id, {})
            pds_val["metal"] += c.get("metal", 0) * cnt
            pds_val["crystal"] += c.get("crystal", 0) * cnt
            pds_val["eonium"] += c.get("eonium", 0) * cnt
        pds_val["total"] = pds_val["metal"] + pds_val["crystal"] + pds_val["eonium"]
        for u_id, cnt in pds_start.items():
            c = pds_cost_map.get(u_id, {})
            pds_val_start["metal"] += c.get("metal", 0) * cnt
            pds_val_start["crystal"] += c.get("crystal", 0) * cnt
            pds_val_start["eonium"] += c.get("eonium", 0) * cnt
        pds_val_start["total"] = pds_val_start["metal"] + pds_val_start["crystal"] + pds_val_start["eonium"]
        for u_id, cnt in pds_surv.items():
            c = pds_cost_map.get(u_id, {})
            pds_val_surv["metal"] += c.get("metal", 0) * cnt
            pds_val_surv["crystal"] += c.get("crystal", 0) * cnt
            pds_val_surv["eonium"] += c.get("eonium", 0) * cnt
        pds_val_surv["total"] = pds_val_surv["metal"] + pds_val_surv["crystal"] + pds_val_surv["eonium"]

        pds_score_start = round(pds_val_start["total"] / 9)
        pds_score_lost = round(pds_val["total"] / 9)
        pds_score_surv = round(pds_val_surv["total"] / 9)

        def_fleets_summary.append({
            "id": "def_pds",
            "name": "Base Planetary Defenses",
            "enabled": True,
            "isPds": True,
            "startCounts": pds_start,
            "lostCounts": pds_lost,
            "survivedCounts": pds_surv,
            "totalStart": tot_start,
            "totalLost": tot_lost,
            "totalSurvived": tot_surv,
            "lossPercent": round((tot_lost / tot_start * 100) if tot_start > 0 else 0, 1),
            "valueStart": pds_val_start,
            "valueLost": pds_val,
            "valueSurvived": pds_val_surv,
            "scoreStart": pds_score_start,
            "scoreLost": pds_score_lost,
            "scoreSurvived": pds_score_surv,
            "scoreDynamics": -pds_score_lost
        })

    # Salvage Calculation (Pegasus Galaxy Official Formula)
    # Salvage = floor(destroyedShips * shipCost * 30 / 100)
    # - Attacker salvage = from destroyed DEFENDER ships -> carried by attacker fleet
    # - Defender salvage = from destroyed ATTACKER ships -> applied immediately to defender planet
    # Both sides always receive their salvage regardless of outcome.
    atk_salvage = {
        "metal": int(def_val_lost["metal"] * 0.30),
        "crystal": int(def_val_lost["crystal"] * 0.30),
        "eonium": int(def_val_lost["eonium"] * 0.30),
    }
    atk_salvage["total"] = atk_salvage["metal"] + atk_salvage["crystal"] + atk_salvage["eonium"]

    def_salvage = {
        "metal": int(atk_val_lost["metal"] * 0.30),
        "crystal": int(atk_val_lost["crystal"] * 0.30),
        "eonium": int(atk_val_lost["eonium"] * 0.30),
    }
    def_salvage["total"] = def_salvage["metal"] + def_salvage["crystal"] + def_salvage["eonium"]

    # Combined salvage dictionary for overall summary
    salvage = {
        "metal": atk_salvage["metal"] + def_salvage["metal"],
        "crystal": atk_salvage["crystal"] + def_salvage["crystal"],
        "eonium": atk_salvage["eonium"] + def_salvage["eonium"],
        "total": atk_salvage["total"] + def_salvage["total"],
        "attacker": atk_salvage,
        "defender": def_salvage,
    }

    # Cargo capacity of surviving attacker ships
    cargo_capacity = sum(
        max(0, g.count) * g.resource_capacity
        for g in attacker_groups
    )

    # Initial Fleet Values for Loot Fairness Factor calculation
    atk_initial_fleet_val = sum(g.initial_count * (g.cost.get("metal", 0) + g.cost.get("crystal", 0) + g.cost.get("eonium", 0)) for g in attacker_groups)
    def_initial_fleet_val = sum(g.initial_count * (g.cost.get("metal", 0) + g.cost.get("crystal", 0) + g.cost.get("eonium", 0)) for g in defender_groups)

    # Dominance & Fairness Factors (Pegasus Galaxy Official Formula):
    # Dominance = defenderShipsDestroyed / defenderShipsStarted
    # DominanceFactor = max(0, min(1, (dominance - 0.2) / 0.6))
    # FleetRatio = attackerFleetValue / defenderFleetValue
    # FairnessFactor = 1 - 0.5 * max(0, min(1, (ratio - 1) / 2))
    # LootMultiplier = DominanceFactor * FairnessFactor
    raw_dominance = (total_def_lost / total_def_start) if total_def_start > 0 else 0.0
    dominance_factor = max(0.0, min(1.0, (raw_dominance - 0.2) / 0.6)) if raw_dominance > 0.2 else 0.0

    fleet_ratio = (atk_initial_fleet_val / def_initial_fleet_val) if def_initial_fleet_val > 0 else 1.0
    fairness_penalty_ratio = max(0.0, min(1.0, (fleet_ratio - 1.0) / 2.0))
    fairness_factor = 1.0 - (0.5 * fairness_penalty_ratio)

    loot_multiplier = dominance_factor * fairness_factor

    # Resource Theft (Plunder): Stolen = floor(defenderStockpile * 0.20 * LootMultiplier)
    # Capped by surviving Resource Hauler cargo capacity. No haulers = no theft.
    def_metal = defender_resources.get("metal", 0)
    def_crystal = defender_resources.get("crystal", 0)
    def_eonium = defender_resources.get("eonium", 0)
    total_def_res = def_metal + def_crystal + def_eonium

    plunder = {"metal": 0, "crystal": 0, "eonium": 0, "total": 0}
    if outcome == "attacker" and total_def_res > 0 and cargo_capacity > 0 and loot_multiplier > 0:
        base_stolen_metal = int(def_metal * 0.20 * loot_multiplier)
        base_stolen_crystal = int(def_crystal * 0.20 * loot_multiplier)
        base_stolen_eonium = int(def_eonium * 0.20 * loot_multiplier)
        base_stolen_tot = base_stolen_metal + base_stolen_crystal + base_stolen_eonium

        if base_stolen_tot <= cargo_capacity:
            plunder["metal"] = base_stolen_metal
            plunder["crystal"] = base_stolen_crystal
            plunder["eonium"] = base_stolen_eonium
            plunder["total"] = base_stolen_tot
        else:
            ratio = cargo_capacity / base_stolen_tot if base_stolen_tot > 0 else 0
            plunder["metal"] = int(base_stolen_metal * ratio)
            plunder["crystal"] = int(base_stolen_crystal * ratio)
            plunder["eonium"] = int(base_stolen_eonium * ratio)
            plunder["total"] = plunder["metal"] + plunder["crystal"] + plunder["eonium"]

    # Asteroid Cargo Capacity of surviving attacker miners
    asteroid_capacity = sum(
        max(0, g.count) * g.asteroid_capacity
        for g in attacker_groups
    )

    # Asteroid Theft (Pegasus Galaxy Official Formula):
    # Stolen = floor(defenderAsteroids * 25 / 100 * LootMultiplier)
    # Capped by surviving Asteroid Miner capacity (5 per miner). No miners = no theft.
    def_metal_roids = int(defender_asteroids.get("metalRoids", defender_asteroids.get("metal", 0)) or 0)
    def_crystal_roids = int(defender_asteroids.get("crystalRoids", defender_asteroids.get("crystal", 0)) or 0)
    def_eonium_roids = int(defender_asteroids.get("eoniumRoids", defender_asteroids.get("eonium", 0)) or 0)
    total_def_roids = def_metal_roids + def_crystal_roids + def_eonium_roids

    stolen_metal_roids = 0
    stolen_crystal_roids = 0
    stolen_eonium_roids = 0

    if outcome == "attacker" and total_def_roids > 0 and asteroid_capacity > 0 and loot_multiplier > 0:
        base_stolen_metal = int(def_metal_roids * 0.25 * loot_multiplier)
        base_stolen_crystal = int(def_crystal_roids * 0.25 * loot_multiplier)
        base_stolen_eonium = int(def_eonium_roids * 0.25 * loot_multiplier)
        base_total = base_stolen_metal + base_stolen_crystal + base_stolen_eonium

        if base_total <= asteroid_capacity:
            stolen_metal_roids = base_stolen_metal
            stolen_crystal_roids = base_stolen_crystal
            stolen_eonium_roids = base_stolen_eonium
        else:
            # Scale down proportionally to fit asteroid cargo capacity
            ratio = asteroid_capacity / base_total if base_total > 0 else 0
            stolen_metal_roids = int(base_stolen_metal * ratio)
            stolen_crystal_roids = int(base_stolen_crystal * ratio)
            stolen_eonium_roids = int(base_stolen_eonium * ratio)
            rem = asteroid_capacity - (stolen_metal_roids + stolen_crystal_roids + stolen_eonium_roids)
            if rem > 0 and stolen_metal_roids < base_stolen_metal:
                add_m = min(rem, base_stolen_metal - stolen_metal_roids)
                stolen_metal_roids += add_m
                rem -= add_m
            if rem > 0 and stolen_crystal_roids < base_stolen_crystal:
                add_c = min(rem, base_stolen_crystal - stolen_crystal_roids)
                stolen_crystal_roids += add_c
                rem -= add_c
            if rem > 0 and stolen_eonium_roids < base_stolen_eonium:
                add_e = min(rem, base_stolen_eonium - stolen_eonium_roids)
                stolen_eonium_roids += add_e
                rem -= add_e

    asteroids_stolen = {
        "metalRoids": stolen_metal_roids,
        "crystalRoids": stolen_crystal_roids,
        "eoniumRoids": stolen_eonium_roids,
        "total": stolen_metal_roids + stolen_crystal_roids + stolen_eonium_roids
    }

    # Official Score Formula (Pegasus Galaxy):
    # Score = 50 * fromRoids + fromResources / 3 + 3 * fromResearches + fromConstructions
    # Where fromResources = (metal + crystal + eonium) / 3  =>  net score per resource = 1 / 9 points.
    # Asteroid score weight: 50 points per roid.
    atk_salvage_pts = int(atk_salvage["total"] / 9.0)
    def_salvage_pts = int(def_salvage["total"] / 9.0)
    plunder_pts = int(plunder["total"] / 9.0)
    stolen_roids_pts = int(asteroids_stolen["total"] * 50)

    # In terms of game score:
    # Attacker net gain = Asteroids (+50/roid) + Plunder (+1/9 per res) + Attacker Salvage (+1/9 per res)
    # Defender net impact = Asteroids (-50/roid) - Plunder (-1/9 per res) + Defender Salvage (+1/9 per res)
    atk_score_delta = stolen_roids_pts + plunder_pts + atk_salvage_pts
    def_score_delta = -stolen_roids_pts - plunder_pts + def_salvage_pts

    score_changes = {
        "attacker": atk_score_delta,
        "defender": def_score_delta,
        "attackerBreakdown": {
            "salvageBonus": atk_salvage_pts,
            "plunderBonus": plunder_pts,
            "asteroidsBonus": stolen_roids_pts
        },
        "defenderBreakdown": {
            "salvageBonus": def_salvage_pts,
            "plunderPenalty": -plunder_pts,
            "asteroidsPenalty": -stolen_roids_pts
        }
    }

    # Win Confidence / Dominance metric (0.0 to 1.0)
    if total_atk_start + total_def_start > 0:
        dominance = max(0.0, min(1.0, (total_def_lost + 1) / (total_atk_lost + total_def_lost + 2)))
        if outcome == "attacker":
            dominance = max(0.65, dominance)
        elif outcome == "defender":
            dominance = min(0.35, dominance)
    else:
        dominance = 0.5

    # Tactical Advice
    advice: List[str] = []
    if outcome == "defender":
        advice.append("⚠️ Assault is projected to fail. Increase total fleet size or send heavy capital ships to absorb ground fire.")
    if current_shield_hp > 0:
        advice.append(f"🛡️ Enemy Shield Generator absorbed significant damage ({int(shield_max_hp - current_shield_hp):,} HP). Bring EMP ships (e.g. Synthara Pulse) or high-caliber bombardment.")
    if cargo_capacity < total_def_res * 0.20 and outcome == "attacker" and total_def_res > 100000:
        advice.append(f"📦 High loot potential ({total_def_res:,} resources on planet)! Your surviving cargo capacity is only {cargo_capacity:,}. Add Freighters/Haulers to maximize plunder.")
    if outcome == "attacker" and total_def_roids > 0:
        max_possible_roids = int(total_def_roids * 0.25 * loot_multiplier)
        if asteroid_capacity == 0:
            advice.append(f"⛏️ Defender has {total_def_roids:,} asteroids available for capture, but your fleet has 0 Mining ships with Asteroid Capacity! Add Ore Extractors, Core Drillers, or Siege Harvesters to seize up to {max_possible_roids:,} asteroids.")
        elif asteroids_stolen["total"] < max_possible_roids:
            advice.append(f"⛏️ Mining ships seized {asteroids_stolen['total']:,} asteroids (capped by {asteroid_capacity:,} asteroid cargo cap). Add more miners to capture the full {max_possible_roids:,} asteroids available.")
    if def_lost_counts.get("main-ion-cannon", 0) == 0 and defender_pds.get("main-ion-cannon", 0) > 0:
        advice.append("⚡ Enemy Ion Cannons will heavily target your capital battleships. Deploy disposable light screens (Talon/Centurion) to draw early fire.")
    if def_start_counts.get("main-vanguard-imperator", 0) > 0:
        advice.append("🛡️ Enemy Imperator deployed! Its Shield Aura absorbs up to 25% of all damage across their entire fleet.")
    if def_start_counts.get("main-ashkari-oblivion", 0) > 0:
        advice.append("💥 Enemy Oblivion deployed! It reflects 15% of damage back at attackers and is completely immune to EMP disruption.")
    if def_start_counts.get("main-synthara-oracle", 0) > 0:
        advice.append("🌀 Enemy Oracle deployed! Cloaked in round 1 and emits fleet-wide EMP disruption waves.")
    if not advice:
        advice.append("✅ Fleet composition is well-balanced for this engagement. Favorable casualty exchange forecast.")

    return {
        "outcome": outcome,
        "outcomeDetail": outcome_detail,
        "rounds": len(round_details),
        "dominance": round(dominance, 3),
        "attacker": {
            "fleets": atk_fleets_summary,
            "startCounts": atk_start_counts,
            "lostCounts": atk_lost_counts,
            "survivedCounts": surviving_atk,
            "totalStart": total_atk_start,
            "totalLost": total_atk_lost,
            "totalSurvived": total_atk_survived,
            "lossPercent": round((total_atk_lost / total_atk_start * 100) if total_atk_start > 0 else 0, 1),
            "valueLost": atk_val_lost,
            "cargoCapacity": cargo_capacity,
            "asteroidCapacity": asteroid_capacity
        },
        "defender": {
            "fleets": def_fleets_summary,
            "startCounts": def_start_counts,
            "lostCounts": def_lost_counts,
            "survivedCounts": surviving_def,
            "totalStart": total_def_start,
            "totalLost": total_def_lost,
            "totalSurvived": total_def_survived,
            "lossPercent": round((total_def_lost / total_def_start * 100) if total_def_start > 0 else 0, 1),
            "valueLost": def_val_lost
        },
        "salvage": salvage,
        "plunder": plunder,
        "asteroidsStolen": asteroids_stolen,
        "scoreChange": score_changes,
        "tacticalAdvice": advice,
        "roundDetails": round_details
    }


# =========================================================================
# TACTICAL DEFENSE INTEL & RELIABILITY HELPERS
# =========================================================================

def evaluate_scan_reliability(scan_dict: Dict[str, Any], current_tick: int) -> Dict[str, Any]:
    """
    Evaluates the reliability index (0-100%) of a scan record based on:
    1. Scan Type: DEEP_SCAN (100%), INCOMING_SCAN (75%), MILITARY_SCAN (80%),
       FLEET_COMPOSITION_SCAN (65%), SURFACE_SCAN (25%).
    2. Freshness / Tick Age: Delta = current_tick - scan_tick.
    3. Cloak / Stealth Vulnerability: Non-Deep scans cannot detect cloaked vessels.
    """
    scan_type = (scan_dict.get("scanType") or "UNKNOWN").upper()
    scan_tick = int(scan_dict.get("tick") or 0)
    
    # 1. Base Scan Type Score
    base_scores = {
        "DEEP_SCAN": 100,
        "MILITARY_SCAN": 80,
        "INCOMING_SCAN": 75,
        "FLEET_COMPOSITION_SCAN": 65,
        "RESEARCH_SCAN": 50,
        "INFRASTRUCTURE_SCAN": 50,
        "RESOURCE_SCAN": 35,
        "SURFACE_SCAN": 25,
        "NEWS_SCAN": 40,
    }
    base = base_scores.get(scan_type, 50)

    # 2. Freshness Multiplier based on tick delta
    delta_ticks = max(0, current_tick - scan_tick) if current_tick > 0 and scan_tick > 0 else 0
    if delta_ticks == 0:
        freshness_factor = 1.0
        freshness_label = "Live (Current Tick)"
    elif delta_ticks <= 1:
        freshness_factor = 0.95
        freshness_label = "Very Fresh (1 tick ago)"
    elif delta_ticks <= 3:
        freshness_factor = 0.85
        freshness_label = f"Recent ({delta_ticks} ticks ago)"
    elif delta_ticks <= 7:
        freshness_factor = 0.70
        freshness_label = f"Aging ({delta_ticks} ticks ago)"
    elif delta_ticks <= 15:
        freshness_factor = 0.45
        freshness_label = f"Stale ({delta_ticks} ticks ago)"
    elif delta_ticks <= 30:
        freshness_factor = 0.25
        freshness_label = f"Old ({delta_ticks} ticks ago)"
    else:
        freshness_factor = 0.10
        freshness_label = f"Obsolete ({delta_ticks} ticks ago)"

    # 3. Cloak / Stealth Detection Risk
    # In Pegasus Galaxy, cloak tech hides ships unless scanned with DEEP_SCAN
    cloak_risk = False
    cloak_penalty = 1.0
    if scan_type != "DEEP_SCAN":
        cloak_risk = True
        cloak_penalty = 0.85  # 15% uncertainty due to stealth/cloaked ships

    # Final Composite Reliability Percentage
    reliability = int(round(base * freshness_factor * cloak_penalty))
    reliability = max(5, min(100, reliability))

    if reliability >= 80:
        rating = "HIGH"
        color = "#86efac"  # Green
    elif reliability >= 55:
        rating = "MODERATE"
        color = "#fde047"  # Yellow
    elif reliability >= 30:
        rating = "LOW"
        color = "#fb923c"  # Orange
    else:
        rating = "UNRELIABLE"
        color = "#f87171"  # Red

    warnings = []
    if cloak_risk:
        warnings.append("⚠️ Non-Deep scan cannot reveal cloaked warships or stealth escorts.")
    if delta_ticks >= 6:
        warnings.append(f"⏳ Scan is {delta_ticks} ticks old. Enemy may have constructed reinforcements or launched fleets.")

    return {
        "score": reliability,
        "rating": rating,
        "color": color,
        "scanType": scan_type,
        "deltaTicks": delta_ticks,
        "freshnessLabel": freshness_label,
        "cloakRisk": cloak_risk,
        "warnings": warnings
    }


def detect_fleet_decoy(fleet: Dict[str, Any], score_intel: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Analyzes an inbound or scanned fleet to evaluate the probability that it is a fake attack,
    scout probe, feint, or decoy fleet.
    """
    ships = fleet.get("ships", {}) or {}
    total_ships = sum(int(c) for c in ships.values() if isinstance(c, (int, float)) and c > 0)
    mission = (fleet.get("mission") or "ATTACK").upper()

    decoy_chance = 0
    reasons = []

    # 1. Zero ships anomaly
    if total_ships == 0:
        return {
            "isDecoy": True,
            "decoyChance": 99,
            "badge": "EMPTY GHOST FLEET",
            "color": "#f87171",
            "reasons": ["Fleet has 0 verified ships (ghost fleet or placeholder signature)."]
        }

    # 2. Single-ship probe / suicide scout
    if total_ships == 1:
        decoy_chance = 95
        reasons.append("Single ship sent on mission (classic scout probe or feint).")
    elif total_ships <= 5:
        decoy_chance = 80
        reasons.append(f"Extremely small force ({total_ships} ships); likely testing defense alarms or pinging PDS.")
    elif total_ships <= 20:
        decoy_chance = 45
        reasons.append(f"Light patrol wing ({total_ships} ships); low combat payload.")

    # 3. Civilian / Non-combat ship composition
    civilian_keys = ["freighter", "runner", "extractor", "driller", "harvester", "transport", "colonizer", "ark", "cargo"]
    combat_keys = ["fighter", "interceptor", "corvette", "destroyer", "cruiser", "battleship", "carrier", "dreadnought", "titan", "colossus", "imperator", "sentinel", "guardian", "centurion", "sovereign"]

    civilian_count = 0
    combat_count = 0
    for sid, count in ships.items():
        sid_lower = sid.lower()
        cnt = int(count) if isinstance(count, (int, float)) else 0
        if any(k in sid_lower for k in civilian_keys):
            civilian_count += cnt
        elif any(k in sid_lower for k in combat_keys):
            combat_count += cnt

    if total_ships > 0 and civilian_count == total_ships and mission == "ATTACK":
        decoy_chance = max(decoy_chance, 90)
        reasons.append("100% civilian transports/extractors on an ATTACK mission — zero offensive weaponry (decoy or plunder diversion).")
    elif total_ships > 0 and (civilian_count / total_ships) > 0.85 and combat_count <= 5 and mission == "ATTACK":
        decoy_chance = max(decoy_chance, 75)
        reasons.append("Predominantly logistical vessels with minimal escort; questionable strike efficacy.")

    # 4. Military Score Correlation
    if score_intel and isinstance(score_intel, dict):
        ships_score = score_intel.get("fromShips", 0)
        if ships_score and ships_score < 10000 and total_ships > 500:
            decoy_chance = max(decoy_chance, 85)
            reasons.append(f"Attacker military ship score ({ships_score:,}) cannot support reported fleet volume ({total_ships:,} ships).")

    is_decoy = decoy_chance >= 60
    if decoy_chance >= 75:
        badge = "HIGH DECOY PROBABILITY"
        color = "#f87171"
    elif decoy_chance >= 40:
        badge = "SUSPECTED FEINT"
        color = "#fb923c"
    elif decoy_chance >= 20:
        badge = "POSSIBLE DIVERSION"
        color = "#fde047"
    else:
        badge = "GENUINE STRIKE"
        color = "#86efac"

    return {
        "isDecoy": is_decoy,
        "decoyChance": decoy_chance,
        "badge": badge,
        "color": color,
        "totalShips": total_ships,
        "civilianCount": civilian_count,
        "combatCount": combat_count,
        "reasons": reasons if reasons else ["Fleet exhibits genuine warship configuration and offensive profile."]
    }


def filter_fleets_by_arrival(fleets: List[Dict[str, Any]], target_tick: int, window: int = 0) -> Dict[str, Any]:
    """
    Partitions fleets into available (arrivesAt <= target_tick + window) and late arrivals.
    """
    available = []
    late = []
    for f in fleets:
        arr = f.get("arrivesAt")
        status = (f.get("status") or "").upper()
        if status in ("DOCKED", "STATIONARY", "ORBIT") or arr is None:
            f_copy = dict(f)
            f_copy["arrivalStatus"] = "DOCKED_NOW"
            f_copy["readyForBattle"] = True
            available.append(f_copy)
        else:
            try:
                arr_tick = int(arr)
            except (ValueError, TypeError):
                arr_tick = 0

            f_copy = dict(f)
            f_copy["arrivalTick"] = arr_tick
            if arr_tick <= (target_tick + window):
                f_copy["arrivalStatus"] = "ARRIVES_IN_TIME"
                f_copy["readyForBattle"] = True
                f_copy["marginTicks"] = (target_tick + window) - arr_tick
                available.append(f_copy)
            else:
                f_copy["arrivalStatus"] = "TOO_LATE"
                f_copy["readyForBattle"] = False
                f_copy["missedByTicks"] = arr_tick - (target_tick + window)
                late.append(f_copy)

    return {
        "targetTick": target_tick,
        "window": window,
        "availableFleets": available,
        "lateFleets": late,
        "availableCount": len(available),
        "lateCount": len(late)
    }

