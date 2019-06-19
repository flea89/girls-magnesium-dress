goog.module('dmb.components.progressGrid.controller');

/**
 * ProgressGrid class controller.
 */
class ProgressGridController {
  /**
   * ProgressGrid controller
   *
   * @param {!Object} tenantConf
   * @param {!Function} dmbLevelsFactory
   *
   * @ngInject
   */
  constructor(tenantConf, dmbLevelsFactory) {
    /**
     * @type {Object}
     * @export
     */
    this.levels = tenantConf.levels;

    /**
     * @type {Object}
     * @export
     */
    this.levelsMax = tenantConf.levelsMax;

    /**
     * @type {Object}
     * @export
     */
    this.levelsArray = tenantConf.levelsArray;

    /**
     * @type {Object}
     * @export
     */
    this.ratingMainData = {};

    /**
    * @type {Object}
    * @export
    */
    this.industryBestData = {};

    /**
     * @type {Object}
     * @export
     */
    this.industryAvgData = {};

    /**
     *
     * @type {Function}
     * @export
     */
    this.dmbLevelsFactory = dmbLevelsFactory;

    // Bind for external use
    this.updateLevelsData = this.updateLevelsData.bind(this);
  }

  /**
   * On scope initialisation update the values
   */
  $onInit() {
    this.updateLevelsData();
  }

  /**
   * Respond to property changes and update the values
   */
  $onChanges() {
    this.updateLevelsData();
  }

  /**
   * updates the levels data for from dmbLevelsFactory
   */
  updateLevelsData() {
    this.ratingMainData = this.dmbLevelsFactory(this.ratingMain);
    this.industryBestData = this.dmbLevelsFactory(this.industryBest);
    this.industryAvgData = this.dmbLevelsFactory(this.industryAvg);
  }

  /**
   * Function to get the progress width/height for the horizontal and vertical bars
   * @param {number} value
   * @return {string}
   * @export
   */
  getProgress(value) {
    if (value) {
      const firstLevel = this.levelsArray[0];
      const firstLevelRange = this.levelsArray[1] - firstLevel;

      // normalise value to 0 by subtracting the firstLevel
      value -= firstLevel;

      // calculate the percetage of bar based on the first level's range
      const prog = (value / firstLevelRange) * 100;
      return `${prog}%`;
    }
  }
}


/** @const {string} */
ProgressGridController.CONTROLLER_NAME = 'ProgressGridCtrl';


/** @const {string} */
ProgressGridController.CONTROLLER_AS_NAME = 'progressGridCtrl';


exports = {
  main: ProgressGridController,
  CONTROLLER_NAME: ProgressGridController.CONTROLLER_NAME,
  CONTROLLER_AS_NAME: ProgressGridController.CONTROLLER_AS_NAME,
};
