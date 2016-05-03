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
		[KRPCProperty]
		public static GegiStream ActiveGegi {
			get { return new GegiStream (); }
		}
	}
}
