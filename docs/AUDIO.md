# Developer Mode vehicle audio

The bundled Skip Barber sound JSON can reference four files absent from its
mounted archive. This affects the vehicle on any track. See the measured
filenames, hashes and trace evidence in [NOTES.md](NOTES.md).

Studio 397 supports [loose 16-bit PCM WAV samples relative to a ModDev
vehicle](https://docs.studio-397.com/display/DG/Using+the+new+sound+engine).
The helper below installs local aliases using existing game recordings. It does
not modify SDK JSON/MAS files or launch the game. This workaround still needs
an in-game check and does not establish that an accompanying crash is resolved.

## Current local installation

Four aliases are installed under rFactor 2's
`ModDev\Vehicles\SkipBarber\sounds`. From the activated project environment:

```bat
python -m ac_to_rf2.sound_aliases --plan out\_maintenance\skipbarber-audio-plan.json
```

This checks the installed aliases without changing them. The local ownership
receipt records the exact files and hashes. To remove only those aliases:

```bat
python -m ac_to_rf2.sound_aliases --undo out\_maintenance\skipbarber-audio-receipt.json
```

Undo refuses to remove changed files and preserves preexisting files. Keep the
receipt. Plans, receipts and extracted recordings stay under ignored `out/`;
game audio is not distributed with this repository.

## Reproduce on another installation

Close rFactor 2. In the official `Support\Tools\MAS2.exe`, open
`ModDev\Vehicles\SkipBarber\SkipBarber_Sounds.mas` and extract its samples into
an ignored working folder, such as `out\_maintenance\skipbarber-export`.
Use Edit → Select All, then Edit → Extract. The measured archive has 83 entries.
The separate archive under `ModDev\Sounds\SkipBarber` was unreadable in this
utility; do not substitute it or try to bypass that restriction.

Create a JSON plan with these fields and absolute paths for your installation:

```json
{
  "rf2": "C:/Program Files (x86)/Steam/steamapps/common/rFactor 2",
  "vehicle": "SkipBarber",
  "sound_config": "skipbarber_snd.json",
  "aliases": {
    "sounds/Skip_TC_in.wav": "C:/Program Files (x86)/Steam/steamapps/common/rFactor 2/ModDev/Sounds/Secondary/tc_in.wav",
    "sounds/Caterham_in_shift.wav": "D:/dev/ac-to-rf2/out/_maintenance/skipbarber-export/skipb_in_shift.wav",
    "sounds/Caterham_ext_startup.wav": "D:/dev/ac-to-rf2/out/_maintenance/skipbarber-export/skipb_ex_startup.wav",
    "sounds/Skip_TC_ext.wav": "C:/Program Files (x86)/Steam/steamapps/common/rFactor 2/ModDev/Sounds/Secondary/tc_ex.wav"
  }
}
```

Save it under `out/` and check it before applying. Use a new receipt path:

```bat
python -m ac_to_rf2.sound_aliases --plan out\audio-plan.json
python -m ac_to_rf2.sound_aliases --plan out\audio-plan.json --apply --receipt out\audio-receipt.json
```

The helper requires each target to be declared by the selected sound JSON,
validates complete 16-bit PCM payloads and refuses different existing files.
It has no built-in vehicle or track special cases. The mappings above substitute
Skip Barber shift/startup recordings and the base game's traction-control
recordings; they are a workaround, not an official restoration of the missing
recordings. Recheck after SDK updates instead of assuming mappings still apply.

## Manual comparison

Use Skip Barber with **zero AI opponents** on bundled Joesville, then on the
converted Laguna Seca. Check whether the warnings disappear and practice loads.
Add AI only after those checks. Preserve the latest `ModDev\UserData\Log\trace_*`
and any new `ModDev\UserData\rFMini.dmp` if a failure remains. No game is launched
by the alias helper.
