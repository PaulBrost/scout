QA/QC Instructions for Item Type – Matching
# Matching: Overview
A Matching item type requires test takers to respond by dragging or clicking choices (sources) and moving them by dropping or clicking again into the appropriate locations or drop zone or drop target (targets).
## Modes of Input:
There are 2 different ways that sources can be moved in a matching item. Both ways should be tested during QC of matching items.
- Drag
- The student drags the sources from the source tray and vice versa by using their finger/stylus, or track pad/mouse.
- Click-Click
- The student uses their finger/stylus, track pad/mouse, or keyboard to move the sources by clicking on them and then clicking on them again where they want them to be placed.
## Types:
- Match SS (Single Select) If only one of the sources can be moved to only one of the targets.

- Match MS (Multiple Select) If multiple sources are being moved to multiple targets.

## Moveable Objects or Sources:
- The moveable objects (sources) can either be authored as text or images and are presented in a source tray, which typically appears above or to the left of the drop zones/drop targets.
- Sources authored as text based appear blue with bold white text.
- Sources are initially presented in row(s) in a source tray and are vertically aligned to the top. A new row begins when there is not enough room on the current row to accommodate all sources.
- Sources can be authored in IBIS to be single use (can only be used once) or multiple use as needed (can be reused for a specified number of times)
## Drop Zones/Targets or Targets:
- Specific areas where the sources can be placed.
- Targets can also be authored in IBIS to allow a single source or multiple sources.
## Various Matching Scenarios:
- Multiple Drop Zones or Targets
- More than one target drop zones available where sources could be placed.

- Multiple Use/Reuse Sources
- Any given source could be reused for any specified number of times.
- Once a reused source is moved, another copy will still appear in the source tray.

- Single use Drop Zone/Target
- Sources when placed in the target will be centered.
- Once a source is placed, moving any new source will result in the existing source returning to the source tray and getting replaced by the new source.

- Multi-use Drop Zone/Target
- Sources are placed in the target left-justified.
- The drop zone will allow new sources to be placed next to the existing source until the maximum number is reached.

- Match Groups
- Sources can be moved to the specific assigned target group ONLY to limit the ways a student can respond.
- There will be separate source trays provided for each source group.
- When moving a source, only the background of the assigned targets area will change to an active state.

# Matching: QC Checklist


|  | Test | Steps to Test | Expected Results |
| --- | --- | --- | --- |
| 1. | Verify that each source can be moved to the target(s). | Move each source to the first target. Repeat this process for all targets, if the item has more than one target.   [Use both drag and click-click functionality to test.] | If the targets permit only one source, then after the target has one source, each new source moved to the target should replace the one that was there. The previous source should appear back in the source tray.    If the targets permit multiple sources, then with each new source moved to the target, the source should stay in the target.   Targets should become visible upon initiating drag or click of source. |
| 2. | Verify that a source can be moved from one target to another (for multiple-select item type only) | Move each source to a target. Then move that source to another target, and to other targets in the item if they exist, and then back to the original target.    [Use both drag and click-click functionality to test.] | Sources should appear in the targets in which they were moved.   Targets should become visible upon initiating drag or click of source. |
| 3. | Verify that each source can be moved from a target back to the source tray. | Move each source to the target(s) and then move the source back to the source tray.     For multiple-select item types, move a source to the first target. Then, move that source from the first target to the second target. Finally, move that source back to the source tray.    [Use both drag and click-click functionality to test.] | Sources should appear in the source tray and in the same location in the tray as they were upon entering the item. |
| 4. | Verify source use (single-use or reusable)    Note: Verification requires a comparison of an IBIS report for source use to the item's functionality in-system. | Move a source to a target.    [Use both drag and click-click functionality to test.] | For single-use sources, the instance of the source should no longer appear in the source tray.     For reusable sources, the instance of the source should still appear in the source tray.    For A/B matching, only the sources designated for the specific drop zones/targets should be allowed to be moved. Once they are moved, they should no longer appear in the source tray. |
| 5. | Verify that answers can be cleared. | Verify Clear Answer button is present. Then, move sources to target(s) and then select Clear Answer.     [Do this test for different sources moved to different targets.] [Use both drag and click-click functionality to test.] | Targets should no longer have sources in them, and the sources should appear back in the source tray in the same location in the tray as they were upon entering the item. |
| 6. | Verify that each answer is retained.     NOTE: This can only be tested in an assembled block. | Move the first source to the first target and then navigate to the next item. Then, navigate back to the matching item.      [Do this test for different sources moved to different targets. In addition, vary your navigation. For instance, go to the next item on some and go to an item that is not the next item (before and after) for others.] [Use both drag and click-click functionality to test.] | The tab for the matching item should turn grey and the item should not appear on the Review tab. Once back to the item, the first source should appear in the first target. |
| 7. | Verify that a cleared answer is NOT retained.     NOTE: This can only be tested in an assembled block. | Move sources to target(s) and navigate to the next item. Then, navigate back to the matching item and select Clear Answer. Navigate to another item and then back to the matching item.    [Do this test on more than one option, but not necessarily all options.] [Use both drag and click-click functionality to test.] | The tab for the matching item should not show as answered, and the target(s) in the item's targets should not have any sources. In addition, the item should appear as not answered on the Review tab. |
| 8. | Verify that the minimum selection feature is functioning correctly for multiple-select item types. | Test 1:  If the item indicates to “move a/an X into each box” and each target (box) supports only 1 source, then move a source to each target and navigate to the next item. Repeat this process by randomly moving sources to the targets.   NOTE: The number of sources will be greater than the number of targets.     Test 2:   If the item indicates to “move each” of the sources and each target supports only 1 source, then move each source to a target and navigate to the next item.   NOTE: The number of sources will be equal to the number of targets.    Test 3:   If the item indicates to “move each” of the sources and each target supports all the sources, then move all sources to the first target. Repeat this process by moving all sources to each target. Lastly, move sources randomly to all the targets until they are placed.   NOTE: the number of sources will be greater than the number of targets.    Test 4:   If the item indicates to move a specific number of sources to one or more targets, then move the specified number of sources to the target(s). Repeat this process by varying which sources are moved to the target(s).   NOTE: The targets only support the specified number of sources as indicated in the item. In some cases, an image, such as a table, may be provided in such a way that only two sources can be placed into one target (the entire table). In other cases, one source can be placed in one of two targets drawn on the image (two targets on the table). The target region(s) will become visible upon initiating the movement of a source.    Test 5:   If the item is a match group variant (for example, star-shaped sources can only be placed in start-shaped targets, and square-shaped sources can only be placed in square-shaped targets), then move sources to targets of corresponding type. In this instance, each target supports only 1 source. Repeat this process by varying which sources are moved to the targets. Lastly, attempt to move sources to non-corresponding target types.  [Use both drag and click-click functionality to test all scenarios.] | Test 1:   The tab for the item should turn grey as an indication that the item has been answered when each target has a source. In addition, the item should not appear on the Review tab.             Test 2:   The tab for the item should turn grey and an indication that the item has been answered when each source has been placed in a target. In addition, the item should not appear on the Review tab.       Test 3:   The tab for the item should turn grey and an indication that the item has been answered when each source has been placed in a target. In addition, the item should not appear on the Review tab.                 Test 4:   The tab for the item should turn grey and an indication that the item has been answered when each target has the number of sources indicated in the item. In addition, the item should not appear on the Review tab.                         Test 5:  The tab for the item should turn grey as an indication that the item has been answered when each target has a source. In addition, the item should not appear on the Review tab. |
| 9. | Verify that scratchwork is NOT permitted over the source tray, sources, and target(s). | Open the scratchwork tool. Using the pen tool, mark over the source tray, sources, and target(s).    [Repeat this test with the highlighter tool.] | Scratchwork should not appear over the source tray, sources, and target(s), nor the space between the source tray and the target(s)    Scratchwork will appear outside the frame in which the sources and target(s) are contained if marks were made in this area. |
| 10. | Verify that TTS is enabled around sources and background image (target) | Open the Text to Speech tool. | Highlighted boxes should appear around each source and around the target area.  Alt text for images should be read aloud. IBIS generated sources do not have alt text but should be read aloud. |
| 11. | Verify that the Text Highlighter tool is NOT permitted on text-based sources (if applicable). | Open the Text Highlighter tool. Using the highlighter, attempt to highlight the source text and the target text. | The source text and the target text should NOT be highlightable in matching items. |
| 12. | Verify that sources and target theme as expected. | Open a matching item. Use the theme tool to change themes.   [Verify default, beige, and dark theme.] | Sources and targets should be the theme as per authored in IBIS.  Sources should not move or be altered when changing themes. |
