# Golden Gate Wi-Fi symbol rendering test

On a MacBookPro9,1 running Golden 26B131, can the Intel HD Graphics 4000 and the NVIDIA GeForce GT 650M draw the same Wi-Fi shape and return the expected pixels? The earlier NVIDIA clear-and-readback test established that a Metal command could fill a surface. This test exercises a fragment shader on both GPUs and checks the shape as well as its background.

## Run from the iMac

Open Terminal in the folder containing `Test-Randare.command`. Replace `login@host` with the SSH login and address you already use for the MacBook. SSH requires the host key to be in your known-hosts file. Enter the login password at the SSH prompt if requested.

```sh
./Test-Randare.command --check
./Test-Randare.command 'login@host'
```

`--check` generates the reference mask on the iMac and verifies the local test inputs. The second invocation checks the target model and build, places the scripts, portable interpreter, mask and shader in a temporary directory on the MacBook, and removes that directory on exit. It uses ordinary user privileges. The existing image, EFI, installed GPU drivers and Finder session can remain in use. For private local configuration, the launcher also accepts `GOLDEN_GATE_SSH` or a sibling `target.txt` containing just the SSH destination.

## How to read the result

The iMac prints the path to a new `GoldenGate-Randare-WiFi-…` folder. Open `comparatie.html` to see the reference and the two GPU readbacks for each operation. `raport.txt` contains the Romanian verdict. The exact input mask is in `wifi-mask.json`, the returned bytes and device identifiers are in `intel.json` and `nvidia.json`, and SSH and target diagnostics are in `sesiune.json`.

| Operation | What the GPU reads |
| --- | --- |
| Texture control (`texture0`) | A separate source texture containing the initial pattern. |
| Framebuffer read (`fetch0`) | The existing color in the destination attachment, at the same pixel. |

Each run starts with a known 32 × 32 RGBA8 pattern. Inside the Wi-Fi mask, the fragment adds 1/16 to each normalized color channel. The background retains its original values. The iMac checks each returned channel against the expected byte value, allowing one unit for rounding. A full pass requires 1,024 matching pixels, including foreground and background.

* **Both GPUs pass both operations.** Each GPU can render this shape through the tested paths. For the Finder symptom, the next discriminating observation is whether an actual IconServices image request reaches rendering, given the recorded XPC peer rejections and error 4097.
* **Both texture controls pass, Intel passes the framebuffer read, and NVIDIA returns incorrect pixels on that read.** This records a difference in framebuffer reads on this configuration. Repeat on the external copy with the same mask and shader before changing NVIDIA compatibility code. A separate Finder capture would be needed to connect the two symptoms.
* **A control has incorrect pixels or both framebuffer reads have incorrect pixels.** The results do not isolate an NVIDIA framebuffer-specific defect. The report identifies which operation and pixels differ.
* **NECONCLUDENT.** A missing GPU, timed-out command, or incomplete readback leaves pixel correctness open. A native Metal error creating `fetch0` with both texture controls passing identifies a failure before drawing. The report preserves the error detail.

## Test boundary and source

The iMac creates a fresh binary mask from the AppKit system symbol `wifi` using `wifi-mask.js`. On the MacBook, `native-metal.py` runs with the project's existing portable x86_64 Python and calls the public Objective-C Metal APIs. The launcher first constructs Metal descriptors and checks the bridge on the target. If that step fails, it selects the same alternative client for both GPUs, `metal-render.js` under `/usr/bin/osascript -l JavaScript`. This client resolves the classes by Objective-C runtime name. The session records the client and preflight result. Each GPU is tested in a separate process. The test draws the mask using the same shader library and scissor rectangles on both devices. The HTML includes the returned pattern and a high-contrast view of the per-pixel changes. The reported Metal registry IDs identify the selected GPUs.

The test measures the graphics path available to the selected client and the target's installed Metal framework. It does not establish the CPU architecture or HAO translation mode of Finder or Control Center, which GPU those applications selected, or whether IconServices delivered an image. A correct standalone render is compatible with a failed Finder XPC request.

Credit for the HAO patcher and its upstream Metal framebuffer probe belongs to **lythka and the upstream contributors**. This Golden Gate test adapts that probe to compare one symbol on the two GPUs. The upstream shader source is pinned to commit `6bd75aab112d1078acd8e75180eb510672461365`. The private local fixture `probe.metallib` was taken from `store/artifacts/mbp91-metal-framebuffer-step10-20261118-013319-672509/probe.metallib` in the project's patcher working copy. For a source-only checkout, place the pinned shader and portable interpreter archive beside the launcher. The local kit already contains both. For the shader, the launcher verifies SHA-256 `faebda663e14aceaef91f9eb51c9a34ce3320b89690e46227d2e2bbb909c380f` on both machines. It loads the existing library without invoking a compiler. [Upstream probe.metal](https://github.com/lythka/hao-patcher/blob/6bd75aab112d1078acd8e75180eb510672461365/patches/golden-gate-metal-framebuffer/build/src/probe.metal)

The experiment uses the x86_64 Python 3.12.14 already present in the image builder. To reproduce the runtime archive from the builder's existing `py-x86_64` directory, run the following from the test folder. The expected archive SHA-256 is `989daf7d002118391328c0caebd5a5baa708454e61ad4c81e0af81eae5fb15f9`.

```sh
/usr/bin/python3 -I -B pack-runtime.py /path/to/kit/py-x86_64 metal-python.tar.gz
```

Golden Gate investigation and local test credits go to **Штефан al Mare** and **OpenAI Codex**.

## Pe scurt, în română

Rulează cele două comenzi de mai sus pe iMac și înlocuiește `login@host` cu destinația SSH a MacBook-ului. Deschide `comparatie.html` din dosarul afișat. Vei vedea aceeași formă Wi-Fi redată separat pe Intel și pe NVIDIA. Dacă trec ambele probe de control și numai NVIDIA întoarce pixeli greșiți la citirea framebufferului, avem o diferență concretă de reprodus pe discul extern. Dacă toate cele patru probe trec, problema icoanelor din Finder rămâne de urmărit pe traseul cererii către IconServices. Testul pornește cu un client Intel x86_64 care accesează direct Metal. Dacă verificarea inițială a acestuia eșuează, lansatorul folosește clientul alternativ pentru ambele plăci. Un rezultat `NECONCLUDENT` înseamnă că lipsește o măsurătoare validă.


## Testing the pre-transformed fetch0 shader on Kepler

Two physical runs on 19 November 2026 reproduced the same result on Golden 26B131. The HD 4000 returned all 1,024 expected pixels with both shaders. The GT 650M passed the separate-texture control and its Metal compiler rejected the original `fetch0` pipeline with `CompilerError` 2, `Unhandled metadata type: air.render_target`. No image was returned for that pipeline.

Run `./Test-Kepler.command login@host` from the test folder to repeat the control and the original shader and then submit the pre-transformed version of the same `fetch0` function to the GT 650M. Each case uses a separate native process. The readback and device IDs are checked on the SSH client. The new report is in a sibling `GoldenGate-Kepler-Fetch-*` folder.

The transformed library is `lowered-single.metallib` (SHA-256 `a993e3c2691da18b8da9460a61a16a59f3b19c86fc726c69dc9a4a33b07f1b2f`). Its companion `lowered-single.bindings.json` declares a single-sample color input named `__fbcompat_fb_attachment_0`, with texture index 127 for `fetch0`. Both files come from the same pinned artifact directory as the original shader and can be copied beside this launcher's scripts when using a source-only checkout. The test uses the pipeline's public argument reflection to bind the input. The expected shape is drawn from a stored source onto a distinct destination. The physical test passed on Golden 26B131. All 175 foreground and 849 background pixels matched within 1/255. The GT 650M reported the texture at index 127. Its compiler rejected the original pipeline in the same session. Finder and Control Center still need their own end-to-end checks. [Upstream reference probe](https://github.com/lythka/hao-patcher/blob/6bd75aab112d1078acd8e75180eb510672461365/patches/golden-gate-metal-framebuffer/build/src/probe.m#L137-L177)

### Proba Kepler în română

Comanda `./Test-Kepler.command login@host` compară pe aceeași GT 650M controlul prin textură, shaderul original și varianta precompilată de autor pentru aceeași funcție. Raportul salvează eroarea compilatorului sau pixelii verificați pentru fiecare probă. Pe GT 650M, varianta adaptată a întors 1.024/1.024 pixeli corecți. Următoarea validare privește pictogramele vizibile și timpul de răspuns al Finder pe copia externă.

## Checking the login window and menu bar

From the iMac, run `./Test-Login-Icons.command --login-only login@host` to summarize retained events around WindowServer startup and the console session. The report prints its timing anchors. A process start may follow a restart within an existing session. It groups explicit `air.render_target` rejections separately from other graphics errors, failed Finder image requests, and IconServices connection rejections. Each count identifies the reporting process or an unattributed compiler service. A GPU name is recorded only when mentioned in the message or sender name. Missing or redacted records leave the GPU assignment open.

În modul `--login-only`, jurnalul se citește din sesiunea deja pornită, fără repornire și fără intervenție pe MacBook. Raportul se salvează pe iMac. Pentru comparația vizuală pe copia externă, se urmăresc Wi-Fi și Bluetooth, un simbol vizibil precum sunetul și pictograma aceluiași volum în Finder.

For the specific 19 November 2026 login, run `./Test-Login-Icons.command --graphics-details login@host` to inspect the historical interval from 16:30:37 to 16:32:56 EET. Each slice reports graphics messages grouped by static template, emitter and technical hints. The first capture counted 33 matching WindowServer records, then timed out during the high-volume Finder and IconServices query. The graphics detail scan also covers the intervening 19 seconds. Each slice reports its own completeness.

Pentru autentificarea din 19 noiembrie 2026, `--graphics-details` citește mesajele grafice din intervalul 16:30:37–16:32:56 EET. Rezultatul arată procesul, componenta emitentă, tipul mesajului și eventualele coduri tehnice disponibile.
