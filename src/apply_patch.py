"""
apply_patch.py  -  adds the TCAXY routing algorithm (mesh + torus) to BookSim 2.
Run from the booksim2/src folder:   python3 apply_patch.py
Safe to run twice (it checks whether the patch is already there).
"""
import re, sys, pathlib

src = pathlib.Path("routefunc.cpp")
cfg = pathlib.Path("booksim_config.cpp")
if not src.exists() or not cfg.exists():
    sys.exit("Run this from booksim2/src (routefunc.cpp not found).")

code = src.read_text()
if "tcaxy_mesh" in code:
    sys.exit("Already patched - nothing to do.")

NEW_CODE = r'''
//=============================================================
// TCAXY : Threshold-biased Congestion-Aware XY/YX routing
// (course-project addition; mesh + 2D torus)
//
//  * Source router looks at the first-hop output port of the XY path and
//    of the YX path (both minimal).
//  * It keeps XY (the default) unless the XY port is more congested than the
//    YX port by MORE than tcaxy_threshold used credits.
//  * The choice is encoded in the VC class (no extra flit field):
//      mesh : XY -> lower half of VCs, YX -> upper half
//      torus: XY/YX halves, each split again by the dateline (needs >=4 VCs)
//=============================================================
static int gTcaxyThresh = 0;

void tcaxy_mesh( const Router *r, const Flit *f, int in_channel,
                 OutputSet *outputs, bool inject )
{
  int vcBegin = 0, vcEnd = gNumVCs-1;
  int out_port;

  if(inject) {
    out_port = -1;
  } else if(r->GetID() == f->dest) {
    out_port = 2*gN;                       // eject
  } else {
    int const half = gNumVCs / 2;
    assert(half > 0);                      // need >= 2 VCs
    int const p_xy = dor_next_mesh( r->GetID(), f->dest, false );
    int const p_yx = dor_next_mesh( r->GetID(), f->dest, true );

    bool x_then_y;
    if(in_channel < 2*gN) {                // already travelling: read order from VC class
      x_then_y = (f->vc < half);
    } else if(p_xy == p_yx) {              // same row/column: no choice
      x_then_y = true;
    } else {                               // source router: congestion-aware choice
      int const c_xy = r->GetUsedCredit(p_xy);
      int const c_yx = r->GetUsedCredit(p_yx);
      x_then_y = !((c_xy - c_yx) > gTcaxyThresh);
    }

    if(x_then_y) { out_port = p_xy; vcEnd   = half - 1; }
    else         { out_port = p_yx; vcBegin = half;     }
  }
  outputs->Clear();
  outputs->AddRange( out_port, vcBegin, vcEnd );
}

// ---- torus helpers (n = 2 only): YX routing = XY routing on swapped coordinates
static inline int tcaxy_swapid( int id )   { return (id % gK) * gK + (id / gK); }
static inline int tcaxy_swapport( int p )  { return (p >= 2*gN) ? p : ((p + 2) % (2*gN)); }

void tcaxy_torus( const Router *r, const Flit *f, int in_channel,
                  OutputSet *outputs, bool inject )
{
  assert(gN == 2);
  int vcBegin = 0, vcEnd = gNumVCs-1;
  int out_port;

  if(inject) {
    out_port = -1;
  } else {
    int const cur  = r->GetID();
    int const dest = f->dest;

    if(cur == dest) {
      out_port = 2*gN;                     // eject, any VC
    } else {
      int const half = gNumVCs / 2;
      assert(half / 2 > 0);                // need >= 4 VCs (order x dateline)

      bool yx;
      if(in_channel < 2*gN) {
        yx = (f->vc >= half);              // order stored in VC class
        if(!yx) {
          dor_next_torus( cur, dest, in_channel, &out_port, &f->ph, false );
        } else {
          int p;
          dor_next_torus( tcaxy_swapid(cur), tcaxy_swapid(dest),
                          tcaxy_swapport(in_channel), &p, &f->ph, false );
          out_port = tcaxy_swapport(p);
        }
      } else {                             // source router: evaluate both orders
        int p_xy, ph_xy, p_yx, ph_yx, tmp;
        dor_next_torus( cur, dest, in_channel, &p_xy, &ph_xy, false );
        dor_next_torus( tcaxy_swapid(cur), tcaxy_swapid(dest),
                        in_channel, &tmp, &ph_yx, false );
        p_yx = tcaxy_swapport(tmp);
        if(p_xy == p_yx) {
          yx = false;
        } else {
          int const c_xy = r->GetUsedCredit(p_xy);
          int const c_yx = r->GetUsedCredit(p_yx);
          yx = ((c_xy - c_yx) > gTcaxyThresh);
        }
        out_port = yx ? p_yx : p_xy;
        f->ph    = yx ? ph_yx : ph_xy;
      }

      // VC class = order half, then dateline sub-half (same idea as dim_order_torus)
      if(yx) vcBegin = half; else vcEnd = half - 1;
      int const avail = (vcEnd - vcBegin + 1) / 2;
      if(f->ph == 0) vcEnd -= avail; else vcBegin += avail;
    }
  }
  outputs->Clear();
  outputs->AddRange( out_port, vcBegin, vcEnd );
}

'''

marker = "void InitializeRoutingMap( const Configuration & config )"
assert marker in code, "InitializeRoutingMap not found"
code = code.replace(marker, NEW_CODE + marker, 1)

code = code.replace("  gNumVCs = config.GetInt( \"num_vcs\" );\n",
    "  gNumVCs = config.GetInt( \"num_vcs\" );\n  gTcaxyThresh = config.GetInt( \"tcaxy_threshold\" );\n", 1)

reg = '  gRoutingFunctionMap["adaptive_xy_yx_mesh"]          = &adaptive_xy_yx_mesh;\n'
assert reg in code, "registration anchor not found"
code = code.replace(reg, reg + '  gRoutingFunctionMap["tcaxy_mesh"]  = &tcaxy_mesh;\n  gRoutingFunctionMap["tcaxy_torus"] = &tcaxy_torus;\n', 1)
src.write_text(code)

c = cfg.read_text()
anchor = '  _int_map["use_read_write"] = 0;'
assert anchor in c, "config anchor not found"
c = c.replace(anchor, '  _int_map["tcaxy_threshold"] = 0;   // TCAXY: credits XY must exceed YX by to switch\n' + anchor, 1)
cfg.write_text(c)
print("Patched routefunc.cpp and booksim_config.cpp. Now run:  make -j4")
