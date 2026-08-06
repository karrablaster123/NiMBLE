#import "@preview/zero:0.6.1": num, format-table, zi, set-round
#import "@preview/subpar:0.2.2"
#import "@preview/showybox:2.0.4": showybox
#import "@preview/drafting:0.2.2": margin-note, inline-note
#import "@preview/lilaq:0.5.0" as lq
#import "@preview/fletcher:0.5.8" as fletcher: diagram, node, edge
#import "@preview/wordometer:0.1.5": word-count, total-words

// See DEFAULT_* for defaults.
#import "@local/template:0.1.0": scaffold, engg_funcs, cancelto, DEFAULT_FONT

#(DEFAULT_FONT.font = "Radio Canada")
// #(DEFAULT_FONT.weight = 350)

#show: scaffold.with(
    title: "SOP: Sulfur Extraction", 
    subtitle: "NiMBLE Project", 
    uvanilla: false,
    font: DEFAULT_FONT,
    // math_font: ??,
    // vanilla_settings: ??,
    // page_settings: ??,
)

#let SDS_link = ("https://www.fishersci.ca/store/msds?partNumber=C573500" +
"&productDescription=carbon-disulfide-spectranalyzed-fisher-chemical" +
"&language=en&countryCode=CA")

#let a = footnote()[Sulfur has a solubility of 0.45 g/mL in CS₂, and therefore, for 1
g of sulfur in a sample, only \~2.2 mL of CS₂ is needed. Use \~10 mL of CS₂.]

#show link: set text(fill: rgb("#0000EE"))
#show link: underline
#show link: strong
#table(columns: (1fr),
  inset: 10pt,
  align: horizon, stroke: rgb("#4A638A"),
  [*Author*: Uddhava Swaminathan],
  [
    *Reagents*: \
    - Carbon Disulfide (#link(SDS_link)[SDS])
    *Glassware & Equipment*: \
    - Aluminum cups (WB353)
    - P4 Grade Filter Paper (WB353)
    - Erlenmeyer/Conical flasks (WB334) (\~50–70 mL)
    - Solids Funnel (WB334)
    - Filter Funnel (WB334)
    - Filter Flask/Vacuum Flask (WB334)
    - Büchner flask (WB334)
    - PTFE (Teflon) Beaker (WB334)
    *PPE*: \
    - Nitrile Gloves
    - Lab Coat
    - Safety Glasses
    - Fumehood
  ],
  [*Safety*\
    The primary concern in this procedure is carbon disulfide (CS₂). Please read the
    SDS before proceeding. CS₂ is highly toxic, flammable, and vaporizes very easily.
    #list(marker: "⚠️",
     [Must be used in a *functioning* fumehood.],
     [Avoid any sources of ignition.],
     [Nitrile gloves are permeable to CS₂.],
       [Double glove to minimize exposure.],
       [Remove the gloves if a large quantity spills on them.],
     [Lower the fumehood sash as much as possible.],)
  ],
  [ *Pre-procedure*\
    + Make sure the weighing scale in WB334 is zeroed and the level bubble is
      correctly centered.
    + Ensure all the samples are dry. Carbon disulfide is not miscible with water and
      water will severely limit sulfur extraction.
    + CS₂ has high surface tension, and an affinity for glass. Transfer an aliquot 
      of CS₂ to the PTFE beaker and pour from this instead.
    + When not in use, close the CS₂ bottle to minimize evaporative losses.
    *Procedure*\
    + Place an Erlenmeyer flask onto the scale and tare.
    + Place a funnel on top of the flask.
    + Add you solids to the flask — \~1–3 g of solids.
    + Remove the funnel and weigh; record the mass added.
    + If the solid is clumped, use a spatula to break it up. Re-weigh the sample if
      any sample was unintentionally removed during crushing.
    + Move the sample to the fumehood and add CS₂ to the sample. Ensure the solids
      are submerged#a.
    + Seal the flask with aluminum foil and gently stir.
    + Leave to rest for 1 hour or more.
    + While the flask rests, take an aluminum cup per sample and weigh it. Record
      its weight and label it appropriately.
    + After the flask has rested, assemble the vacuum filtration equipment. The
      filter funnel fits into the mouth of the filter/vacuum flask. 
    + Attach the vacuum pipe to the flask and turn on the vacuum.
    + Place a leaf of filter paper on top of the funnel. The vacuum should hold the
      paper in place.
    + Place the Büchner flask on top of the funnel to create a watertight seal and
      secure with the clamp.
    + Check the assembly to ensure everything is secure and stable.
    + Remove the foil from the sample flask and gently swirl the glass to suspend the
      solids.
    + Pour the mixture into the Büchner flask. The liquid should pass through
      unimpeded and the solids should be retained back.
    + Rinse the Erlenmeyer flask twice with a little CS₂, pouring it back into the
      flask each time to minimize losses.
    + Set the flask aside inside the fumehood.
    + Carefully shut off the vacuum as you pull the pipe off the flask. Turning off
      the vacuum before removing the pipe can cause water to enter the vessel, and
      thus, this should be avoided.
    + Disassemble the clamp, Büchner flask, and funnel.
    + Carefully pour the filtrate from the filter flask into the appropriate
      aluminum cup. Remember that pouring too fast can lead to splashes and spills,
      and pouring too slowly can lead to the CS₂ streaming down the side of the glass
      flask.
    + Similar to the Erlenmeyer flask, add small amounts of CS₂ and rinse the filter
      flask. Pour this CS₂ into the cup too.
    + Leave the cup inside the fumehood for the CS₂ to dry. This can take anywhere
      from 3 to 6 hours.
    + The evaporation of the CS₂ can cause cold water to condense onto the cup. If
      this happens, the best option is to also wait for the water to evaporate. If
      that is not possible, wait for all the CS₂ to evaporate and then place the cup
      in the 40°C oven for the water to dry. *Remember, CS₂ is extremely flammable,
      and thus this step should only be done if absolutely _necessary_ and with the
      utmost care.*
    + Finally, weigh the dry aluminum cup. If all the steps have been executed
      correctly and there was sulfur present in the sample, there will be yellow
      crystals in the cup and it should weigh more. Record the total weight and
      subtract from the cup weight to compute the sulfur mass.
    + Enter the data on the Solid Sulfur sheet on the NiMBLE data tracking excel with
      the associated sample number.
  ],
)

