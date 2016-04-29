using UnityEngine;
using UnityEngine.UI;
using KRPC.Service;
using KRPC.Service.Attributes;

/// <summary>
///  http://krpc.github.io/krpc/extending.html
/// </summary>
/// 
namespace kRPCGegi
{
	/// <summary>
	/// Service for efficient status retrieval
	/// </summary>
	[KRPCService (GameScene = GameScene.Flight)]
	public static class Gegi
	{
		/// <summary>
		/// Find out max ratio of current temperature to max temperature for all parts
		/// </summary>
		/// <value>The temppct</value>
		[KRPCProperty]
		public static float MaxTempPct {
			get {
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
}
