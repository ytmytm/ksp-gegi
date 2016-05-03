using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using KRPC.Continuations;
using KRPC.Service;
using KRPC.Service.Attributes;

// vs=conn.add_stream(conn.gegi.active_gegi_stream.max_temp_pct)
// vs()

namespace kRPCGegi
{
	[KRPCClass (Service = "Gegi")]
	public sealed class GegiStream
	{
		// empty constructor
		public GegiStream () { }
		/// <summary>
		/// Find out max ratio of current temperature to max temperature for all parts
		/// </summary>
		/// <value>The temppct</value>
		[KRPCMethod]
		public float MaxTempPct() {
				var maxpct = 0f;
				foreach (var part in FlightGlobals.ActiveVessel.parts) {
					var mx1 = part.temperature / part.maxTemp;
					var mx2 = part.skinTemperature / part.skinMaxTemp;
					if (mx1 > maxpct) {
						maxpct = (float)mx1;
					}
					if (mx2 > maxpct) {
						maxpct = (float)mx2;
					}
				}
				return maxpct;
		}
	}
}

